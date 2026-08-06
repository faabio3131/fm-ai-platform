# Plano de migração gradual para o núcleo de Pedidos V1

Complementa a [arquitetura principal](arquitetura-operacional-v1.md). Este documento planeja; **não autoriza nem contém migration**.

## Objetivos e invariantes

* Preservar integralmente `Venda` e relatórios existentes.
* Introduzir Pedido por expansão aditiva, sem renomear/remover coluna/tabela na V1.
* Nunca tocar banco real a partir de teste ou script de desenvolvimento.
* Nenhuma Venda nova vinculada pode baixar estoque duas vezes.
* Rollback desliga a rota nova; dados já escritos permanecem legíveis e reconciliáveis.

## Riscos descobertos

1. `app.py` executa `Base.metadata.create_all` no import e concentra modelos/UI/transações.
2. Venda atual representa simultaneamente item, pagamento e fato financeiro; uma compra multi-item vira várias linhas.
3. Estoque e cashback são saldos mutados diretamente no PDV; Mica também cria Venda e baixa estoque.
4. `Float`, status livres e SQLite não garantem precisão/concorrência esperadas.
5. Mica assume pagamento aprovado, usa fallback para primeiro produto e baixa ficha apenas do último produto.
6. Dashboard soma todas as vendas, sem conciliação de pagamento.
7. Não há `empresa_id`; adicionar multiempresa exige estratégia explícita e contexto confiável.

## Fases e gates

### 0. Preparar e medir

Inventariar ambientes, engine/versionamento, volume, constraints e integrações. Definir owner, janela, RPO/RTO e runbook. Criar backup consistente e **provar restore** em ambiente isolado. Baseline: contagem e somas de Venda por dia/método, estoque, clientes e cashback; checksum por faixa de IDs. Gate: restore dentro do RTO e testes atuais verdes.

### 1. Extrair contratos sem persistência

Adicionar tipos, schemas, relógio/IDs, serviços puros, estados e tabela de decisão, sem importar `app.py` nem alterar fluxo. Testar tenant/RBAC/idempotência. Gate: zero diff funcional e cobertura de contratos.

### 2. Expandir schema (PR futuro e autorizado)

Criar tabelas novas e colunas nulas/indexes online: inclusive `Venda.pedido_id`, `origem`, `status` sem alterar defaults legados. Introduzir empresa/unidade com mapeamento explícito da instalação atual para tenant raiz; contexto vem de autenticação, não do payload. Não criar FK NOT NULL até preenchimento validado. Gate: migration upgrade/downgrade ensaiada em cópia, locks medidos e checksums iguais.

### 3. Escrita sombra

Feature flags por empresa/unidade/canal: `orders_shadow_write`, `orders_read_projection`, `orders_authoritative`, `stock_ledger_authoritative`. PDV legado continua autoritativo; adapter gera Pedido sombra e vínculo, sem publicar para KDS, sem gerar segunda Venda/baixa/cashback. Job compara produto, quantidade, total, cliente, pagamento e timestamps. Falha sombra não pode perder Venda; vai à fila de reparo. Gate: ≥99,99% conciliado por período acordado, zero efeito duplicado.

### 4. Vertical slice do PDV

Ativar Pedido autoritativo para coorte interna. Serviço cria Pedido; adapter de compatibilidade materializa Venda atual uma única vez pelo critério financeiro. Estoque escolhe uma fonte por flag: no início preserva baixa legada; depois ledger assume e o caminho legado deixa de baixar para a coorte. Dashboard recebe visão unificada `UNION`/projeção com origem, evitando dupla contagem. Gate: totais, estoque e cashback conciliados; rollback testado.

### 5. Leitura e operação novas

Central/KDS primeiro em leitura; depois comandos. Migrar salão, entrega, Mica e canais externos separadamente, por coorte. Cada canal tem canary, SLO, DLQ vazia e reconciliação diária. Mica só muda quando resolução estrita e confirmação estiverem prontas.

### 6. Consolidação não destrutiva

Tornar Pedido padrão após período estável. Venda legada segue consultável; não inventar pedidos retroativos, salvo importação explicitamente marcada `legado` e sem efeitos. Constraints são fortalecidas apenas após relatório de nulos/órfãos. Remoção de código/colunas é uma release posterior, com autorização própria.

## Compatibilidade dos dados

| Dado atual | Tratamento |
|---|---|
| Venda existente | permanece `origem=legado` por interpretação da aplicação; `pedido_id` nulo é válido |
| Produto/Cliente/Insumo/Ficha | IDs preservados; novos itens armazenam snapshot e FK opcional |
| Status pagamento livre | mapear em projeção, preservar valor original; divergências vão para revisão |
| Valores Float | não reescrever histórico; converter para Decimal na borda com regra documentada e comparar tolerância de centavo |
| Estoque atual | saldo inicial do ledger em instante de corte + hash; não reproduzir baixas antigas |
| Cashback | saldo inicial e futuro ledger/reserva; conciliar antes/depois |
| Dashboard | visão explícita legado + novo, deduplicada por vínculo/origem |
| Cliente sem consentimento | operacional somente; marketing bloqueado até prova válida |

## Cutover e rollback

1. Congelar configuração, tirar backup/checkpoint e registrar baseline.
2. Habilitar canary por tenant/unidade/terminal, nunca global primeiro.
3. Observar erro, latência, divergência, duplicidade, backlog outbox e saldo negativo.
4. Se limite excedido: desligar `orders_authoritative`, manter dados novos, drenar/reconciliar eventos e voltar ao adapter legado.
5. Não executar downgrade destrutivo. Compensar efeitos confirmados e documentar incidentes.

## Validação e reconciliação

```text
por período/canal:
Σ total Pedido elegível = Σ Venda nova vinculada
Σ pagamentos confirmados - estornos = recebível/caixa por método
saldo inicial + entradas - reservas - consumos + liberações = disponível
Venda vinculada -> exatamente um critério financeiro
origem de estoque -> no máximo uma baixa efetiva por insumo/versão
```

Relatórios listam órfãos, vínculos múltiplos, centavos divergentes, eventos presos, saldo negativo e pedidos concluídos sem Venda/critério. Toda correção é idempotente e auditada.

## Backup, privacidade e segurança

Backups criptografados, acesso mínimo, retenção definida e teste periódico de restauração. Cópias para homologação são anonimizadas; tokens, mensagens e endereços não são copiados desnecessariamente. Scripts exigem URL explícita de ambiente permitido e abortam em hostname de produção sem procedimento humano aprovado.

## Definition of done da migração V1

* Restore provado e runbooks aprovados.
* Vendas/relatórios legados inalterados e consultáveis.
* Novas vendas rastreiam Pedido e critério financeiro.
* Zero dupla baixa/venda/cashback em testes e reconciliação.
* Canary e rollback executados com evidência.
* Isolamento multiempresa e autorização negativos verdes.
* Nenhuma operação destrutiva pendente ou automática.
