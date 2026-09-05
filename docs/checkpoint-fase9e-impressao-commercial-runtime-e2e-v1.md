# CHECKPOINT FASE 9E — IMPRESSÃO — COMMERCIAL RUNTIME E2E V1

**Projeto:** Kordena / GERENTE AI V1.0  
**Issue:** #75  
**PR:** #79 — draft  
**Branch:** `recovery/v1-fase9d-impressao-adapter-config-ui`  
**SHA técnico validado:** `20a80f9d8f1c479ad95091d0537795a29503f80e`  
**Data:** 04/09/2026  
**Status:** F9-E comercial fechada tecnicamente; gate físico/manual de impressora diferido para a homologação final da V1.

## 1. Escopo comprovado

A F9-E comprovou no runtime comercial real, sem `FM_AI_TEST_MODE`, a cadeia:

`login comercial → Pedido → KDS → spool → adapter RAW TCP → persistência de impressão → reimpressão → RBAC`

O teste utilizou PostgreSQL 16, migrations oficiais, `app.py` comercial, identidade real do runtime, composição real de KDS/impressão e transporte TCP efetivo contra um listener de captura de bytes. Nenhum Fake de impressora, `runtime_teste` ou migration test-only entrou no caminho comercial.

## 2. Evidência autoritativa

**Workflow:** `Fase 9E Impressao Commercial Runtime E2E Gate`  
**Run:** #16  
**Run ID:** `33908356204`  
**Job:** `PostgreSQL + app.py + KDS + spool + RAW TCP + RBAC`  
**Job ID:** `101138594119`  
**Resultado:** SUCCESS

Provas duráveis no mesmo run:
- o job original de `pedido-f8e` persistiu como `impresso`;
- `tentativa = 1` no job original;
- foi persistida exatamente uma reimpressão em estado `pendente`;
- a reimpressão ficou vinculada ao job original por `reimpressao_de`;
- o listener RAW TCP capturou **165 bytes**;
- o payload TCP contém `pedido-f8e` e `Burger F8-E`;
- o navegador COZINHA concluiu a jornada comercial;
- o navegador GARCOM recebeu negativa de RBAC ao tentar reimprimir;
- a evidência PostgreSQL posterior confirmou que o GARCOM não criou mutação indevida adicional.

## 3. Correções que tornaram o gate determinístico

Durante a F9-E foram eliminados falsos positivos e falsos negativos do navegador sem relaxar a prova de negócio:

1. a composição comercial KDS → impressão foi conectada ao caminho real do navegador;
2. os controles do Playwright foram escopados ao `tabpanel` visível do Streamlit;
3. mensagens transitórias deixaram de ser tratadas como substitutas de evidência durável;
4. o feedback de processamento/reimpressão passou a sobreviver ao `st.rerun()`;
5. a UI passou a expor explicitamente o estado autoritativo do job selecionado, independente do rótulo cacheado do selectbox;
6. a prova PostgreSQL + RAW TCP passou a ser executada separadamente e de forma obrigatória;
7. o cenário GARCOM só é aceito com prova de ausência de mutação indevida.

## 4. Matriz transversal

No SHA técnico `20a80f9d8f1c479ad95091d0537795a29503f80e`:
- **35/35 workflows SUCCESS** após reexecução controlada do único job transitório;
- F9-B: SUCCESS;
- F9-C: SUCCESS;
- F9-D: SUCCESS;
- F9-E: SUCCESS;
- Commercial Runtime Readiness V1: SUCCESS;
- Wave0 Production Foundation: SUCCESS;
- Wave1 Authoritative Transactions: SUCCESS;
- Wave1 PDV Browser: SUCCESS;
- Wave2 KDS: SUCCESS;
- F8-E KDS Commercial Runtime: SUCCESS;
- PR10 a PR22 relevantes: SUCCESS.

O primeiro attempt do `PR11 Salao Gates` teve um timeout transitório no teste legado CRM/PDV cashback ao selecionar um cliente no combobox. Os jobs Python e Salão estavam verdes; a reexecução do mesmo job, sem alteração de código, passou integralmente. Por isso não foi introduzida alteração especulativa no helper E2E compartilhado.

## 5. O que NÃO foi homologado

Este checkpoint **não** representa teste físico de uma impressora real.

O listener RAW TCP prova transporte de rede e payload real, mas não prova:
- impressora física energizada/conectada;
- compatibilidade de modelo/firmware;
- papel, corte, largura, encoding e qualidade de saída;
- comportamento de rede/local físico do estabelecimento.

Portanto:
- `physical_printer_hardware_gate_pending` permanece;
- `physical_test` permanece `null` no readiness;
- `impressao_operacional` permanece `CUTOVER_PENDING`;
- a Fase 9 não recebe homologação física nem cutover final ainda.

## 6. Decisão de continuidade — pendência diferida

Por decisão de execução de 04/09/2026, o B9-06b — teste físico/manual com impressora real — passa a ser tratado como **pendência diferida para a fase final de homologação da V1**, no mesmo regime operacional das homologações externas que dependem de ambiente/provedor real, como Mercado Pago, Meta e PagBank.

Essa decisão:
- **não fecha** o B9-06b;
- **não remove** `physical_printer_hardware_gate_pending` do readiness;
- **não preenche** `physical_test` sem evidência real;
- **não promove** `impressao_operacional` para `COMMERCIAL_HOMOLOGATED`;
- **não autoriza** merge ou deploy;
- **não bloqueia** o avanço para a próxima fase técnica do Documento Mestre.

O gate físico deverá ser executado na homologação final assim que houver impressora real disponível, registrando modelo, conexão, destino/setor, ticket impresso, reimpressão e comportamento de contingência.

## 7. Próxima fase liberada

Com o Commercial Runtime E2E da Fase 9 validado e o único bloqueio restante formalmente diferido, fica liberado o avanço para **Fase 10 — Expedição/Entregador**, obedecendo o protocolo RECOVERY: inventário Current → Target antes de qualquer implementação.

Até a homologação final:
- PR #79 permanece draft;
- sem merge;
- sem deploy;
- nenhuma migration nova foi criada;
- merge/deploy continuam dependentes de autorização humana explícita.
