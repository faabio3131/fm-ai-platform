# Serviços de estado e política de cozinha — V1

## Escopo e arquitetura

`core.estados` contém serviços puros, sem banco, UI, gateway, KDS ou efeitos em
estoque/Venda. `app.py` e as flags de Pedido permanecem inalterados. Persistência e
publicação externa ficam para adapters posteriores.

## Máquinas normativas

`MAQUINAS` reproduz exclusivamente as transições de
`maquinas-de-estado-v1.md` para Pedido, Pagamento, Comanda, Produção e Entrega.
Qualquer aresta ausente retorna `transicao_<agregado>_invalida`; os terminais
retornam `estado_terminal` e nunca reabrem. O início de Produção apenas gera
`producao.iniciada`: não consome estoque.

## Comando, pré-condições e erros

Cada `ComandoTransicao` informa destino, versão esperada, chave idempotente,
timestamp com fuso, contexto autenticado, pré-condições e, quando excepcional,
motivo. Pedido valida itens/preços, confirmação, roteamento, decisão de cozinha,
início e resolução da produção. Comanda valida saldo e pedidos resolvidos.
Cancelamento exige motivo. Outros erros estáveis incluem
`precondicao_nao_atendida`, `cozinha_nao_autorizada`, `motivo_obrigatorio`,
`recurso_indisponivel`, `permissao_insuficiente`, `conflito_idempotencia` e
`<agregado>_concorrente`.

## Concorrência e idempotência

A versão esperada deve coincidir e cada sucesso incrementa exatamente uma versão.
O registro in-memory associa agregado e chave ao fingerprint do comando. Repetição
idêntica devolve o mesmo evento marcado como idempotente; conteúdo divergente é
conflito e nunca cria evento adicional.

## Autorização e auditoria

O serviço delega autorização a `AutorizarAcao`, `Permissao`, `Papel` e
`PoliticaAlcada`, preservando deny-by-default e a resposta uniforme para acesso
cross-tenant/unidade. Gerente IA não confirma ações críticas. Cada sucesso entrega
um `EventoAuditoria` in-memory com ator, papel, ação, estados, motivo, tenant,
unidade, correlação/causação, horário e política. Metadata passa pelo sanitizador
de segurança.

## Eventos

Cada resultado contém intenção de evento com tenant, unidade, agregado, versão,
tipo, timestamp, ator, correlação, causação e chave idempotente. Os nomes seguem a
tabela normativa, incluindo nomes especiais de reabertura, início, confirmação e
conclusão. Não há publicação externa.

## Política e matriz de cozinha

`PoliticaCozinha` é versionada por `policy_id/version` e selecionada pelo chamador
por canal, origem, momento de pagamento e risco. A função
`pode_enviar_para_cozinha` sempre retorna `DecisaoCozinha`, nunca `bool`, contendo
código, justificativa, risco, confirmação/papel exigidos e metadata segura.

A matriz cobre presencial (Pix, dinheiro e cartão), mesa/comanda no fechamento,
delivery próprio pré-pago ou na entrega, marketplace pago ou gerenciado
externamente e telefone/manual. Pagamento posterior somente passa quando a
política o permite; risco alto, estoque insuficiente, pagamento pendente obrigatório
e confirmação humana ausente bloqueiam. Override requer política habilitada,
papel configurado e `pedido.liberar_cozinha`; Gerente IA é explicitamente excluído.

## Invariantes, riscos e não escopo

Pagamento pago não move Pedido. Produção pronta não conclui Pedido. Entrega
concluída não confirma Pagamento. Comanda somente fecha com saldo/pedidos
resolvidos, e Pedido depende da decisão de cozinha em vez de um estado financeiro
universal. O registro de idempotência é deliberadamente in-memory; produção,
concorrência e seleção de políticas deverão ganhar ports/adapters transacionais em
entregas futuras. Não há migration, alteração do banco real, PDV, Mica, Venda,
cashback, dashboard, estoque, KDS ou integração externa nesta entrega.
