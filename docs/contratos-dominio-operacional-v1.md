# Contratos do domínio operacional V1

## Propósito e estrutura

`core/dominio` fornece a linguagem comum, pura e imutável da operação. IDs ficam em
`ids.py`; valores monetários em `dinheiro.py`; tempo e clocks em `tempo.py`; estados
normativos em `enums.py`; tipos escalares em `tipos.py`; erros em `erros.py`; mensagens
em `comandos.py` e `eventos.py`; visões de leitura em `snapshots.py`; e a decisão
auditável da cozinha em `decisoes.py`. Nenhum módulo conhece UI, ORM ou banco.

## Decisões e invariantes

* IDs são classes nominais imutáveis. Mesmo texto em `PedidoId` e `ClienteId` não é igual.
* `Dinheiro` usa `Decimal`, BRL por padrão e `ROUND_HALF_UP` em duas casas. Valores
  negativos são representáveis porque estornos e ajustes precisam deles; o contexto
  futuro decide quando os proibir. `float` é rejeitado explicitamente.
* Instantes ingênuos são rejeitados e todo instante é normalizado para UTC. Código de
  domínio recebe um `Clock`; produção usa `SystemClock` e testes usam `FixedClock`.
* Enums persistem valores minúsculos estáveis, independentes de rótulos de interface.
* Comandos, eventos e snapshots usam dataclasses congeladas e versão de schema `1`.
* `DecisaoCozinha` garante coerência entre `permitido` e códigos iniciados por
  `permitido_`. A matriz que produz a decisão não faz parte desta entrega.

## Serialização e exemplo

`para_dict()` é a fronteira única: ID vira string, enum vira valor, `Decimal` vira string
decimal (nunca `float`) e datetime vira ISO 8601 UTC terminado em `Z`. Dicionários são
ordenados para eventos determinísticos. Consumidores devem reconstruir tipos usando os
construtores explícitos e respeitar `versao`; alterações incompatíveis exigem nova versão.

```python
from core.dominio.dinheiro import Dinheiro

total = Dinheiro("0.10") + Dinheiro("0.20")
assert total.para_dict()["valor"] == "0.30"
```

## Compatibilidade, limites e próximos PRs

Esta PR somente adiciona contratos, testes e documentação. Ela não integra `app.py`,
PDV ou Mica; não cria entidades mutáveis, handlers, repositories, máquina de estados,
outbox, tabelas, migrations, telas ou políticas executáveis. Tenant e unidade obrigatórios
preparam o isolamento multiempresa, mas autenticação/autorização e resolução confiável do
contexto continuam responsabilidade das futuras camadas de aplicação.

Próximas entregas devem importar estes contratos sem duplicar strings de estado, validar
o tenant a partir de contexto confiável (não apenas do cliente) e converter contratos nas
fronteiras. A adoção deve permanecer incremental; rollback desta PR é a remoção isolada de
`core/dominio`, seus testes e este documento, sem qualquer ação no banco.
