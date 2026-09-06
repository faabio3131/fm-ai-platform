# Fase 13 — Inventário Current → Target — CRM / Cashback / Consentimento V1

## Autoridade e baseline

- Documento Mestre / Recovery Issue #62 continuam soberanos.
- Baseline técnico desta fase: `6500a157de4cda8af07d80f4714f795a3e51b00b` — checkpoint F12-C certificado com 18/18 workflows verdes.
- Branch de execução: `recovery/v1-fase13-crm-cashback-consent-cutover`.
- Nenhum merge, deploy ou produção é autorizado por este inventário.

## Objetivo da F13

Tornar CRM, consentimento e cashback comercialmente canônicos, removendo as duas pendências internas registradas no readiness:

1. `crm_direct_legacy_cashback_write`;
2. `crm_marketing_fake_runtime`.

A conclusão interna da F13 exige uma única autoridade para saldo/movimentos de cashback, consentimento real append-only no banco comercial, marketing negado por padrão e ausência de Fake/Mock/runtime de teste no caminho comercial.

## Current — o que já existe e deve ser reutilizado

### Domínio CRM

O núcleo `core/crm` já possui contratos maduros e não deve ser reescrito:

- `ClienteCRM` com escopo tenant/unidade;
- contatos apenas por referência segura `contact://` / `vault://`;
- consentimento append-only com canal, finalidade, base legal, prova por hash, idempotência e correlação;
- opt-out e re-opt-in explícitos;
- marketing negado por padrão;
- clientes de marketplace restritos e conversão consentida;
- `BeneficioCRM` e `TipoBeneficioCRM.CASHBACK` para emissão de benefícios;
- funil CRM e auditoria;
- eventos de consentimento via outbox.

`core/crm/runtime_teste.py` é composição exclusivamente em memória para testes. Ele não é uma composição comercial válida e continuará isolado ao ambiente de testes.

### Persistência CRM já existente

Reutilizar:

- `infra/crm/clientes_sqlalchemy.py`;
- `infra/crm/contatos_sqlalchemy.py`;
- `infra/crm/consentimentos_sqlalchemy.py`;
- schemas auxiliares CRM;
- migrations `0022` a `0026` relacionadas a cliente, contact vault, mapping legado, ownership e histórico de consentimentos;
- migration `0034_crm_customer_context_v1` quando aplicável ao contexto compartilhado do cliente.

A migration `0026_crm_consentimentos_historico_v1` já define `crm_consentimentos_v1` como autoridade histórica append-only. Não criar segunda tabela de consentimento.

### PDV / pagamento já existente

O PDV já finaliza pagamentos pela orquestração canônica de Pedido/Pagamento/Venda Financeira. A reconciliação registra `cashback_usado` e `cashback_ganho`.

Porém `application/pdv_legacy_projection.py` ainda debita e credita diretamente `infra.legacy_schema.clientes.saldo_cashback` após liquidação. Hoje, portanto, o saldo econômico ainda pertence à projeção legada.

### UI comercial atual

`app.py` ainda:

- lê `Cliente.saldo_cashback` como saldo disponível;
- adiciona crédito manual com `c_up.saldo_cashback += valor_add_cb` e commit direto;
- valida o cashback do PDV contra o saldo legado;
- usa o saldo legado para calcular desconto;
- mantém caminho de campanha/resgate capaz de chamar `mock_whatsapp_send` em test mode.

Esses comportamentos explicam os blockers atuais e não podem permanecer como autoridade comercial ao fechar a F13.

### Campanhas governadas do Gerente IA

`application/campanhas_governadas.py` governa aprovação/publicação humana das campanhas do Gerente IA. Ele não executa transporte externo de marketing. Deve continuar como boundary de governança e não ser substituído pelo CRM.

A execução CRM deve consumir somente campanhas/ações autorizadas e ainda aplicar a regra de consentimento do destinatário.

## Lacunas comprovadas

### 1. Cashback não possui ledger comercial canônico completo

`PortaBeneficiosCRM` atualmente possui apenas `emitir(...)`. `BeneficioCRM` representa emissão positiva, mas não há contrato persistente equivalente para:

- crédito operacional/manual;
- ganho decorrente de compra;
- débito/resgate no PDV;
- saldo atual derivado;
- listagem/auditoria dos movimentos;
- idempotência do débito financeiro concorrente.

Portanto não é seguro apenas trocar a leitura de `saldo_cashback` por `PortaBeneficiosCRM`: o ciclo econômico ficaria incompleto.

### 2. Não foi encontrada persistência SQLAlchemy de benefícios/cashback

`infra/crm` contém clientes/contatos/consentimentos, mas não possui adapter comercial correspondente a `PortaBeneficiosCRM` com ledger durável.

É necessária persistência canônica aditiva. Nenhuma migration histórica será alterada.

### 3. PR19 não protege o cutover comercial completo

O workflow `PR19 CRM Gates` atualmente executa Ruff/mypy/testes de `core/crm` e a suíte completa, mas não possui fitness test específico que impeça:

- mutação direta de `saldo_cashback` em `app.py`;
- uso de `mock_whatsapp_send` pelo CRM comercial;
- composição de `RuntimeCRMTeste` no runtime comercial.

A F13 deve adicionar um boundary/fitness gate permanente.

### 4. Marketing comercial ainda não possui boundary de envio real/fail-closed na UI CRM

`ServicoCRM.despachar_marketing` já verifica consentimento antes de chamar `PortaEnvioMarketing`, mas a UI comercial não está composta sobre uma implementação comercial governada dessa porta.

Enquanto WhatsApp externo não estiver homologado, a solução interna deve poder registrar/encaminhar a intenção governada de envio por canal real/outbox ou falhar fechado — nunca simular sucesso com fake no caminho comercial.

## Target — autoridade desejada

### Cashback

Criar um ledger canônico append-only de movimentos de cashback, scoped por tenant/unidade/cliente, com:

- identificador único do movimento;
- tipo de movimento explícito (`credito`, `debito`);
- origem/referência (`compra`, `manual`, `conversao`, `ajuste_governado`, etc.);
- valor monetário Decimal positivo;
- idempotency key única por scope;
- correlation/reference quando houver;
- timestamp UTC;
- saldo calculado a partir dos movimentos, nunca armazenado como segunda autoridade mutável.

Regras:

- débito não pode exceder o saldo disponível;
- débito deve bloquear/serializar a leitura do saldo dentro da transação para impedir double-spend;
- replay da mesma idempotency key retorna o mesmo efeito sem duplicar saldo;
- crédito e débito do PDV devem ocorrer no mesmo limite transacional da finalização/reconciliação aplicável;
- `clientes.saldo_cashback` legado poderá continuar temporariamente como projeção de compatibilidade, mas nunca como fonte de decisão.

### CRM / consentimento

- `crm_clientes_v1` e `crm_consentimentos_v1` permanecem autoridades existentes;
- clientes legados usados no CRM comercial devem ter mapping/regularização explícitos para `ClienteCRM`;
- consentimento deve ser consultado no banco comercial antes de qualquer marketing;
- revogação deve surtir efeito imediatamente;
- nenhum dado cru de contato/prova deve vazar para auditoria/outbox.

### Marketing

- a UI não chama fake;
- ação comercial passa por application boundary e `ServicoCRM`;
- sem consentimento: bloqueia;
- com consentimento e transporte real disponível: envia por porta comercial;
- com consentimento mas provedor externo indisponível/não homologado: estado interno permanece explícito/fail-closed ou enfileirado conforme infraestrutura canônica, sem falso “enviado”.

### UI / PDV

`app.py` deve:

- consultar saldo pelo boundary CRM/cashback canônico;
- registrar crédito manual somente pelo boundary transacional;
- validar desconto do PDV contra saldo canônico;
- nunca atualizar `Cliente.saldo_cashback` diretamente;
- nunca chamar `mock_whatsapp_send` no fluxo CRM comercial.

A projeção legada, enquanto necessária a compatibilidade de Fase 6, deve receber o saldo resultante a partir da autoridade canônica ou ser reconciliada sem participar da decisão.

## Estratégia de execução

### F13-A — Ledger e persistência canônica

1. Evoluir o contrato do domínio sem quebrar emissão de benefício existente.
2. Implementar ledger/movimentos de cashback e cálculo de saldo.
3. Criar adapter SQLAlchemy.
4. Criar migration aditiva posterior a `0038` e registrá-la no runner/manifest sem alterar migrations históricas.
5. Cobrir concorrência/idempotência/saldo insuficiente/crédito/débito.

### F13-B — Application boundary e composição comercial

1. Criar boundary transacional CRM/cashback reutilizando `UnitOfWorkV1` / `RecursosTransacionaisV1`.
2. Compor clientes, consentimentos, cashback e auditoria reais.
3. Integrar ganho/resgate do PDV à autoridade canônica no ponto de finalização econômica.
4. Manter projeção legada apenas como compatibilidade não autoritativa.

### F13-C — Cutover UI e marketing

1. Remover leitura/escrita autoritativa de `saldo_cashback` no `app.py`.
2. Remover `mock_whatsapp_send` do caminho CRM comercial.
3. Passar campanhas/resgates pelo consentimento canônico e boundary de envio governado/fail-closed.
4. Preservar fakes apenas nos entrypoints/composições de teste.

### F13-D — Certificação

1. Fitness gate permanente para proibir regressão ao legado/fake.
2. PR19 CRM Gates.
3. PR22 Marketing Governance Gates.
4. gates PDV/Fase 6 impactados.
5. suíte Python completa.
6. Commercial Runtime E2E CRM → cashback → PDV → liquidação → saldo.
7. teste de opt-out/negação de marketing.
8. atualizar readiness somente depois das evidências do mesmo SHA.

## Não fazer

- não reescrever `ServicoCRM` funcionando;
- não alterar migrations históricas `0022`–`0026`;
- não criar segunda autoridade de consentimento;
- não manter `saldo_cashback` legado como fallback silencioso;
- não considerar `RuntimeCRMTeste` produção;
- não tratar fake de WhatsApp como homologação;
- não acoplar o ledger ao Gerente IA;
- não misturar homologação externa do WhatsApp com conclusão do ledger interno;
- não fazer merge/deploy/produção sem gate humano.

## Definition of Done interna da F13

A F13 interna só pode ser declarada concluída quando:

- `crm_direct_legacy_cashback_write` = eliminado;
- `crm_marketing_fake_runtime` = eliminado do runtime comercial;
- saldo canônico deriva do ledger persistente;
- não existe double-spend sob concorrência suportada;
- replay idempotente não duplica crédito/débito;
- PDV decide e liquida cashback pela autoridade canônica;
- consentimento é consultado na autoridade append-only real;
- marketing sem consentimento continua negado;
- todos os gates aplicáveis ficam verdes;
- readiness reflete exatamente o runtime observado.

Pendências exclusivamente externas de transportes de marketing, se ainda existirem, devem ser registradas separadamente e não podem mascarar pendência interna.