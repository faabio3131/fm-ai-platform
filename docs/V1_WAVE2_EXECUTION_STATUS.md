# V1 Onda 2 — Estado de execução

## Dependência externa mantida como pendente

`PAY-002 / PagBank` permanece **PENDENTE POR DEPENDÊNCIA EXTERNA** na Onda 1.

Motivo atual: aguardar acesso à conta PagBank para obtenção/validação de nova credencial Sandbox. Esta pendência não será tratada como concluída, não será substituída por mock e não autoriza o cutover do PIX real no PDV.

Enquanto essa dependência externa estiver aberta, o desenvolvimento pode continuar apenas em frentes independentes previstas no backlog da V1, sem promover a Onda 2 para produção e sem mergear a PR50.

## Escopo da Onda 2

Ordem documental:

1. `CENTRAL-001` — Central de Pedidos operacional, persistente, Core-managed e alimentada pelos estados canônicos de Pedido.
2. `KDS-001` — KDS/cozinha derivado do fluxo canônico, sem estado paralelo conflitante.
3. `SAL-001` — Salão/mesas/comandas persistentes e integrados ao Core.
4. `GAR-001` — operação de garçom com permissões, escopo de unidade e trilha auditável.
5. `PRINT-002` — impressão operacional derivada de eventos canônicos, evitando PII financeira desnecessária.

## Regras de execução

- V2 permanece congelada.
- Nada fake/protótipo será marcado como concluído.
- A Onda 2 será desenvolvida em PR draft empilhada sobre a PR50.
- Nenhuma PR será mergeada sem validação funcional/manual e aprovação explícita.
- A Onda 2 não será promovida ao runtime comercial enquanto a Onda 1 mantiver pendências bloqueantes.
- Central, KDS, Salão e Garçom devem reutilizar Pedido/Estados/Eventos autoritativos da Onda 1, sem criar uma segunda verdade de pedido.

## Definition of Done aplicada a cada item

Cada item somente pode ser considerado concluído quando estiver visível, operacional, persistente, Core-managed, integrado, seguro, testado, sem comportamento fake de produção, utilizável pelo restaurante e observável.

## Ponto de partida

Branch: `impl/v1-wave2-restaurant-operations`

Base: `impl/v1-wave1-authoritative-transactions` / PR50.

Head-base no início desta Onda 2: `ccc59d669ee8ffe9ba8c671bbc4199de1beab7f4`.

Próxima ação: inventariar o runtime existente de Central/KDS/Salão/Garçom/impressão e iniciar `CENTRAL-001` pelo fluxo canônico de Pedido.
