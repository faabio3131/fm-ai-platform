# Interface do garçom V1 — PR12

## Objetivo

Entregar uma interface operacional enxuta para celular e tablet sobre os domínios já autoritativos de `Pedido`, KDS e Salão. A interface do garçom não cria uma nova fonte de verdade: ela projeta mesas/comandas já existentes e avisos de itens prontos do KDS.

## Escopo

- painel responsivo para celular e tablet;
- mesas livres e comandas sob responsabilidade do atendente;
- abertura de comanda, participantes, vínculo de pedido, solicitação de conta e retomada do consumo por meio de `ServicoSalao`;
- atualização periódica da projeção;
- aviso de produção `pronta` somente quando o `pedido_id` pertence a uma comanda visível ao atendente;
- alçadas explícitas por papel;
- E2E em viewport de celular e tablet.

## Não escopo

- captura ou confirmação de pagamento;
- fechamento financeiro da comanda pelo garçom;
- estorno, desconto acima de limite ou alteração de caixa;
- transferência/junção/separação quando o papel não possui a permissão correspondente;
- mutação direta do estado do KDS a partir do aviso de pronto;
- deploy ou migration em banco real.

## Invariantes

1. Todo acesso é escopado por `tenant_id + unidade_id`.
2. Para `Papel.GARCOM`, comandos de alteração só podem atingir comandas cujo `responsavel_id` é o próprio `usuario_id`.
3. Mesas livres podem aparecer para abertura; comandas de outro garçom não podem ser alteradas pela interface do garçom.
4. Gerente/administrador podem visualizar o painel completo e usar suas alçadas existentes; a PR12 não amplia a matriz de permissões.
5. Avisos de pronto são derivados de itens KDS com `status == pronta` e filtrados por pedidos efetivamente vinculados às comandas visíveis.
6. A UI nunca converte um aviso de pronto em `producao.retirada`; retirada continua submetida à máquina de estados e RBAC do KDS.
7. Atualização automática é somente leitura. Falha de atualização não autoriza escrita offline nem replay inventado.
8. `Pedido`, `Pagamento`, `Venda`, KDS e Salão permanecem domínios autoritativos em seus respectivos limites.

## Alçadas

### Garçom

Permissões usadas da matriz existente:

- `pedido.criar`;
- `pedido.visualizar`;
- `pedido.alterar`;
- `mesa.abrir`;
- `comanda.alterar`.

A interface adiciona uma restrição de responsabilidade: mesmo possuindo `comanda.alterar`, o garçom não atua em comanda de outro responsável.

### Gerente/administrador

Podem visualizar todas as comandas do escopo e continuam sujeitos às permissões normativas já existentes. A interface pode sinalizar ações que exigem gerente/caixa, mas não assume essas alçadas.

## Atualização e aviso de pronto

O painel recompõe sua projeção em intervalos curtos no runtime de teste. O aviso contém somente identificadores operacionais mínimos: mesa, comanda, pedido, setor e horário de pronto. Não replica dados de cliente nem detalhes financeiros desnecessários.

## Acessibilidade

- controles com rótulos textuais;
- ações críticas não dependem somente de cor;
- ordem de leitura linear em viewport estreito;
- cartões e botões ocupam largura disponível no celular;
- foco do E2E em 390×844 e 820×1180;
- estados e avisos possuem texto explícito.

## Feature flag

`FM_AI_GARCOM_V1=1` somente quando `FM_AI_TEST_MODE=1`. Fora do runtime de teste a flag falha fechada nesta etapa.

## Observabilidade e auditoria

PR12 não cria escrita paralela. As mutações delegadas ao `ServicoSalao` mantêm os eventos/idempotência/auditoria já definidos no domínio de Salão. O painel pode contabilizar leituras e avisos apenas como métricas locais/testáveis, sem PII.

## Rollout e rollback

Nesta PR o rollout é restrito a teste/CI. Rollback executável: desabilitar `FM_AI_GARCOM_V1`. Não há migration própria da PR12.

## Gates

- Ruff e mypy do escopo PR12;
- testes unitários de alçada e filtragem de pronto;
- integração multi-tenant/responsabilidade;
- suíte Python completa;
- E2E celular e tablet por papel;
- regressão das PR10 e PR11.

Nenhum gate autoriza merge, deploy, migration real ou início da PR13 automaticamente.