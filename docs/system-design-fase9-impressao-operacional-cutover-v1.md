# SYSTEM DESIGN FASE 9 — IMPRESSÃO OPERACIONAL — CUTOVER COMERCIAL V1

**Issue:** #75  
**Base:** `591c08bace3467b0cedbc827b12396fc8d49bcae`  
**Status:** F9-A — design de cutover aprovado para execução sequencial, não congelamento global

## 1. Princípio arquitetural

Impressão é um **side effect operacional opcional** do KDS. Ela não participa da
máquina normativa de Produção e não pode ser condição de sucesso para o KDS.

A regra principal é:

`Pedido/KDS commitam independentemente -> integração idempotente cria spool -> worker/adapter imprime`.

Nunca:

`impressora -> decide ou bloqueia transação KDS`.

## 2. Autoridades

- Pedido: Pedido V1.
- Produção/setor: KDS V1.
- Spool: `core/impressao`.
- Autorização: RBAC/ContextoExecucao.
- Auditoria: RepositorioAuditoria canônico.
- Transação de impressão: Application + UnitOfWorkV1.
- Hardware: implementação de `PortaImpressora`.
- Configuração de destino: fonte comercial tenant/unidade/setor.

## 3. Componentes alvo

### 3.1 Application boundary
Criar boundary dedicada, sem `commit()` em UI/service/repository, para:
- enfileirar impressão a partir de produção já persistida;
- processar job;
- reimprimir;
- listar/consultar spool.

### 3.2 Integração KDS
A integração deve consumir fato já confirmado do KDS (roteamento/produção criada)
e produzir um job idempotente. Replay do mesmo fato retorna o mesmo job.

A indisponibilidade da impressão:
- pode registrar falha/contingência do spool;
- não desfaz KDS;
- não altera versão/estado de Produção;
- não impede operador de seguir no KDS.

### 3.3 Configuração de destinos
Resolver por:
`tenant_id + unidade_id + setor_id -> impressora_id + ativo + max_tentativas + provider`.

A fonte deve ser governada, auditável e fail-closed. Configuração de outro tenant
ou unidade nunca pode ser resolvida por fallback global silencioso.

### 3.4 Adapter físico
`PortaImpressora` permanece o contrato.

O adapter comercial deve:
- receber somente ticket minimizado;
- normalizar falhas para erro de impressão estável;
- possuir timeout;
- não persistir credenciais no job;
- não vazar exceção bruta/segredo;
- não executar retry infinito;
- não assumir commit de banco.

A escolha de tecnologia física (spool do SO, rede/IPP/RAW ou serviço local)
será feita em F9-D conforme ambiente de implantação, sem acoplar o domínio.

### 3.5 UI comercial
Superfície mínima:
- fila/spool por status/setor;
- indicação de contingência;
- detalhe sem PII desnecessária;
- ação de reimpressão com motivo;
- RBAC `impressao.reimprimir`;
- nenhuma capacidade de alterar KDS.

## 4. Transações e consistência

O KDS e o hardware não formam uma transação distribuída.

Modelo:
1. KDS confirma seu estado na própria UoW;
2. fato canônico fica observável;
3. integração de impressão cria/deduplica job;
4. job é persistido;
5. processamento físico ocorre fora da transação KDS;
6. resultado físico atualiza somente o spool.

Isso evita rollback de Produção por falha de hardware.

## 5. Idempotência e concorrência

Preservar:
- `dedup_key`;
- `documento_hash`;
- CAS por `versao`;
- conflito explícito para mesma chave/documento divergente;
- reimpressão como novo job referenciando o original.

O idempotency key de integração deve derivar de fato KDS estável, e não de
timestamp aleatório da UI.

## 6. Segurança e privacidade

Ticket não deve conter:
- telefone/endereço;
- cartão/Pix;
- token/credencial;
- dados financeiros;
- segredos de provider.

Tenant/unidade são obrigatórios em toda leitura/escrita.

`ImpressoraFake` é proibida no commercial default por fitness gate.

## 7. Migration

O schema `impressao_jobs_v1` já é criado pela migration comercial oficial
`0012_restaurant_operations_runtime_v1`.

Regra F9:
- não reutilizar `migrations/impressao_v1.py` em produção;
- não criar migration nova por conveniência;
- criar migration somente se a configuração comercial de destinos exigir
  persistência nova e o drift for demonstrado/documentado antes.

## 8. Resiliência

- retry limitado;
- contingência terminal automática do job;
- KDS sempre disponível independentemente da impressora;
- provider ausente/config inválida: fail-closed da impressão;
- observabilidade suficiente para ação humana;
- reimpressão manual governada após restabelecimento.

## 9. Gates

### F9-B
Composition/UoW + anti-Fake + migration/schema + regressões.

### F9-C
KDS -> spool, replay/idempotência, isolamento e prova de não bloqueio.

### F9-D
Provider/configuração real, timeout/contingência, UI/RBAC.

### F9-E
PostgreSQL + runtime comercial + browser + hardware real no mesmo SHA quando
hardware estiver disponível.

## 10. Rollback

- desligar `FM_AI_PRINT_V1` remove a superfície/efeito executável;
- jobs já existentes permanecem auditáveis;
- desabilitar provider/destino não altera KDS;
- nenhuma impressão física já realizada é “desimpressa” por rollback;
- rollback de código não apaga spool histórico.

## 11. Não escopo

- reescrever KDS;
- transformar impressão em autoridade;
- substituir Pedido/Estoque/Pagamento/Entrega;
- criar fila global paralela ao Event Bus sem necessidade;
- homologar hardware inexistente por simulação;
- merge/deploy automático.
