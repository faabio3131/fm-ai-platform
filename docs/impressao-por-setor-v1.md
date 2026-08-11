# Impressão opcional por setor V1

## Objetivo

A PR14 adiciona uma camada **opcional** de impressão operacional por setor sobre o KDS V1. O KDS continua sendo a superfície padrão e a fonte operacional da produção. Impressão é uma conveniência de contingência/apoio e não passa a controlar Pedido, Produção, Estoque, Pagamento ou Entrega.

## Fluxo

1. Um item já roteado para um `SetorProducao` pode gerar um job de impressão.
2. O destino é resolvido por `tenant_id + unidade_id + setor_id`.
3. O ticket é renderizado com dados mínimos de produção e gravado no spool.
4. O worker/adaptador tenta imprimir fora da transação do KDS.
5. Falhas ficam no domínio de impressão, com retry limitado e estado `contingencia` ao esgotar as tentativas.
6. Reimpressão cria um novo job explícito, exige motivo, permissão e auditoria persistida pelo `RepositorioAuditoria`.

## Invariantes

- KDS permanece padrão e autoritativo para Produção.
- Falha de impressora **nunca altera estado ou versão do KDS** e não bloqueia transições de produção.
- Job automático é idempotente por escopo, setor, chave de idempotência e versão de template.
- Repetição idêntica retorna o mesmo job; mesma chave com documento diferente é conflito explícito.
- Reimpressão é idempotente por ação, referencia o job original e não modifica o documento original.
- Reimpressão exige `impressao.reimprimir`; Cozinha, Gerente e Administrador possuem a alçada base. Gerente IA não recebe essa permissão.
- Todo acesso ao spool é escopado por tenant/unidade.
- CAS por versão impede atualização perdida do job persistente.

## Conteúdo do ticket e privacidade

O renderer não consulta nem recebe campos estruturados de endereço, telefone, pagamento, cartão, PIX ou credenciais. O ticket contém somente setor, identificador do pedido, descrição operacional do item, quantidade, identificador de produção e observação operacional opcional.

Não há payload de pagamento, segredo, token ou credencial no spool. Erros de driver são normalizados para `impressora_indisponivel`; exceções brutas não são persistidas no job.

## Persistência e deduplicação

A PR14 oferece:

- adapter em memória para testes determinísticos;
- adapter SQLAlchemy aditivo para spool durável;
- unicidade de `dedup_key` no escopo tenant/unidade;
- optimistic locking/CAS por `versao`;
- índices por status e setor.

A migration `migrations/impressao_v1.py` é **test-only**: aceita somente SQLite em memória ou arquivo explicitamente identificado como teste e rejeita `banco_erp_local.db`.

Nenhuma migration em banco real está autorizada por esta PR.

## Reimpressão auditada

A reimpressão exige:

- job original no mesmo tenant/unidade;
- motivo operacional não vazio;
- chave de idempotência;
- autorização RBAC `impressao.reimprimir`;
- repositório de auditoria explícito no serviço.

A primeira solicitação cria e persiste um `EventoAuditoria` com referência ao job original, setor e motivo sanitizado. Retry idempotente não cria novo job, nova auditoria nem novo efeito físico.

## Contingência

Cada destino possui `max_tentativas` entre 1 e 10. Uma falha marca `falhou`; ao atingir o limite, o job entra em `contingencia`. Esse estado encerra novas tentativas automáticas daquele job, mas a fila KDS continua normalmente.

A operação deve tratar a contingência por procedimento local: acompanhar o KDS e, após restabelecimento da impressora, solicitar reimpressão autorizada quando necessário.

## Feature flag

`FM_AI_PRINT_V1=1` só habilita a funcionalidade quando `FM_AI_TEST_MODE=1`. Fora do runtime de teste a flag é fail-closed nesta etapa.

## Adaptador físico

A PR14 define a porta `PortaImpressora` e usa `ImpressoraFake` nos testes. Não instala driver, não acessa spool do sistema operacional e não envia dados a impressoras reais. Um adapter físico é uma decisão de implantação e requer configuração/credenciais/rede próprias e autorização de deploy.

## Rollback

- desabilitar `FM_AI_PRINT_V1` remove a funcionalidade executável;
- jobs existentes permanecem auditáveis e não afetam KDS;
- downgrade de schema é permitido somente no banco efêmero/teste;
- não há rollback automático de impressão física já realizada.

## Critérios de aceite da PR14

- roteamento por setor;
- deduplicação persistente;
- retry limitado e contingência;
- reimpressão autorizada, idempotente e auditada de forma persistida;
- isolamento multiempresa/unidade;
- falha da impressão não bloqueia nem modifica KDS;
- testes unitários, integração, suíte Python e regressões anteriores verdes.
