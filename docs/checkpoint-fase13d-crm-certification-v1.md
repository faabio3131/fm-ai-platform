# F13-D — Checkpoint de Certificação Interna CRM/ Cashback / Consentimento

## Autoridade

- Programa Recovery: Issue #62.
- Branch: `recovery/v1-fase13c-crm-ui-marketing-cutover`.
- Nenhum merge, deploy ou início de F14 é autorizado por este checkpoint.

## Escopo certificado pelo gate F13-D

O checkpoint somente pode ser declarado concluído quando o mesmo HEAD provar, em CI:

1. Ruff com zero violações no escopo F13 e no executor canônico alterado pelo cutover.
2. mypy no boundary F13 e no executor canônico sem erros.
3. suíte Python completa com zero FAIL.
4. readiness inventory reconciliado com o código.
5. PostgreSQL staging efêmero sem `FM_AI_TEST_MODE`.
6. cadeia CRM -> cashback canônico -> PDV autoritativo -> liquidação -> saldo canônico e projeção legada compatível.
7. marketing WhatsApp negado sem consentimento, sem chamada ao transporte.
8. ausência de regressão nos gates já homologados/certificados da Recovery.

O repositório possui dívida histórica de lint fora do escopo da F13; por isso este checkpoint não declara
`ruff check .` global como baseline. A certificação exige zero violações nos arquivos F13, no executor
canônico tocado pelo cutover e nos testes de certificação, sem enfraquecer os gates existentes dos demais
módulos.

## Autoridade econômica

- O ledger canônico de cashback é a autoridade econômica.
- `clientes.saldo_cashback` permanece somente como projeção de compatibilidade.
- O PDV canônico síncrono e a finalização assíncrona usam o boundary canônico de cashback antes da projeção legada.
- O CRM comercial não chama `runtime_teste` e não usa transporte fake.
- `core/crm/runtime_teste.py` exige explicitamente `FM_AI_TEST_MODE=1` e falha fechado fora do test runtime.

## Readiness

Após o saneamento F13-C, `crm_cashback` pode avançar para `COMMERCIAL_CANDIDATE` quando `code_blockers=[]` estiver reconciliado com o checker. A homologação externa de WhatsApp Cloud API continua pendente e impede `COMMERCIAL_HOMOLOGATED`.

## Evidência imutável

O SHA final e os IDs dos workflows do mesmo SHA devem ser registrados na descrição da PR #99 após a conclusão verde da matriz. Esse registro não altera o código e evita criar um novo SHA apenas para documentar o próprio hash.
