# WP-031 — Fiscal V1 Complete — System Design & Authority Map

**Status:** WP-031A→L implementados/certificados; WP-031 Master Gate PENDING / NÃO INICIADO
**Date:** 20/09/2026
**Repository:** `faabio3131/fm-ai-platform`
**PR:** #118 — OPEN/DRAFT
**Branch:** `feat/web-parity-v1-total-original-migration`
**Kordena HEAD de discovery:** `41aa7a8cb2326ad4d91c20f4541da66a6c3b7d3f`
**Fiscal V1 baseline congelado:** `faabio3131/kordena-fiscal-engine@b336def47ad4f5188307102203f4e04b98406014`
**Decisão de sequência:** WP-031 Fiscal antes do Visual Premium final.

## 1. Objetivo

Completar o Fiscal V1 e integrá-lo ao Kordena sem reconstruir autoridades existentes. O WP-031 cobre:

1. Outbound Fiscal — documentos de saída vinculados à venda canônica.
2. Inbound Fiscal — documentos recebidos, DF-e, XML e manifestação.
3. Fiscal Procurement — fornecedor, compra, recebimento, matching, estoque, custo e devolução.
4. Fiscal Accounting / Control Bridge — obrigações, reconciliação e base governada para créditos/escrituração.
5. Smart Fiscal Intake — DF-e, XML, PDF, imagem e câmera convergindo para um único pipeline.

O Visual Premium permanece bloqueado até o WP-031 Master Gate.

## 1.1 Decisão de versão fiscal

A Kordena V1 usa exclusivamente o Fiscal Engine V1 congelado em `b336def47ad4f5188307102203f4e04b98406014`.

O **FM Fiscal / NFCore V2 não substitui o Fiscal V1 nesta fase**. A migração para NFCore V2 pertence à evolução futura da Kordena V2 e exigirá bloco próprio, gates próprios e decisão explícita de promoção.

## 2. Autoridades congeladas

### 2.1 Kordena

| Domínio | Autoridade CURRENT | Decisão WP-031 |
|---|---|---|
| Pedido | Core/Application canônico do Kordena | Preservar |
| Pagamento | `core/pagamentos` | Preservar |
| Venda reconhecida | `VendaFinanceira` + `reconhecer_venda()` | Gatilho outbound |
| Evento de venda | `venda.criada` | Entrada do Fiscal Bridge |
| Estoque | `core/estoque` + boundary legado certificado | Preservar movimentos; integrar recebimento sem segunda autoridade |
| Catálogo | catálogo/ficha técnica existente | Preservar; fiscal apenas vincula perfil |
| Tenant/unidade | sessão/contexto canônico | Preservar |
| RBAC | `core/seguranca/permissoes.py` | Estender, não duplicar |
| Step-up | barreira administrativa existente | Reutilizar |
| Integrações/segredos | Control Plane + Secret Store/Vault existentes | Reutilizar |
| Auditoria | autoridade canônica existente | Reutilizar |
| IA de leitura | `AplicacaoLeituraVisualEstoqueV1` | Reutilizar como interpretação, não autoridade fiscal |

### 2.2 Fiscal V1

O baseline `b336def...` é a autoridade fiscal desta V1 e contém FISC-00 a FISC-19. Não copiar regras para o Kordena.

São reutilizados, entre outros:

- domínio fiscal canônico;
- Fiscal Profile;
- Fiscal Product Profile;
- Tax Rule Engine;
- lifecycle/state machine;
- idempotência;
- numeração;
- CertificateReference/FiscalSigner boundary;
- XML/XSD;
- FiscalGateway;
- NFC-e/NF-e/NFS-e;
- DANFE/QR;
- cancelamento/consulta/inutilização;
- outbox/contingência;
- archive;
- reconciliação;
- RTC IBS/CBS/IS + multi-UF readiness.

## 3. Achados CURRENT

### 3.1 Outbound

`reconhecer_venda()` já persiste `VendaFinanceira` de forma idempotente e emite `venda.criada` com tenant, unidade, pedido, pagamento, valor, critério e correlation id.

**Decisão:** o Fiscal nunca nasce diretamente do browser nem de webhook isolado de PSP. O gatilho canônico é a venda reconhecida.

### 3.2 Estoque

O ledger canônico possui `TipoMovimento.ENTRADA` e `DEVOLUCAO`, idempotência lógica, tenant/unidade e versionamento.

A superfície Web de estoque também mantém um boundary legado certificado para insumos/validades/custos.

**Decisão:** recebimento fiscal deve terminar na autoridade de estoque existente. Não criar ledger fiscal de estoque paralelo.

### 3.3 Leitura visual já existente

`AplicacaoLeituraVisualEstoqueV1` usa IA para extrair itens de imagem e atualmente chama `aplicar_lote_leitura()` diretamente.

Esse comportamento é válido como capacidade histórica, porém é insuficiente para o novo inbound fiscal porque OCR não pode declarar verdade fiscal nem recebimento físico.

**Target:** câmera/imagem/PDF passa pelo Smart Fiscal Intake. A IA gera uma captura preliminar; XML/DF-e oficial prevalece para campos fiscais; humano confirma recebimento físico; só então ocorre entrada real em estoque.

### 3.4 Compras/fornecedores

Na discovery inicial existia a permissão `compra.aprovar` no RBAC, mas não havia autoridade canônica materializada para pedido de compra, fornecedor ou recebimento fiscal.

**CURRENT pós-WP-031G:** a segunda descoberta dirigida confirmou a ausência. Foi criada uma única autoridade canônica de procurement, integrada ao ledger de estoque existente e preparada para o bridge financeiro do WP-031H, sem criar efeitos financeiros antecipados.

### 3.5 Integrações e segredos

O Kordena já possui catálogo de serviços externos, configuração por tenant/unidade, homologação governada, step-up e `EncryptedSQLAlchemySecretStore`.

**Decisão:** certificado, CSC e credenciais de provider reutilizam esse Control Plane. É proibido criar cofre fiscal paralelo.

## 4. Arquitetura alvo

```text
                           KORDENA
                              |
              +---------------+----------------+
              |                                |
        VendaFinanceira                  Fiscal Purchase Intake
              |                                |
          venda.criada             DF-e/XML/PDF/Imagem/Câmera
              |                                |
              v                                v
       Outbound Mapper                  Inbound Normalizer
              |                                |
              +---------------+----------------+
                              |
                     KordenaFiscalBridge
                              |
                    Fiscal Engine V1
                              |
         +--------------------+--------------------+
         |                    |                    |
   Persistence Adapters   Signer Adapter      Gateway Adapter
         |                    |                    |
   DB/Archive/Outbox       Secret Store        Provider/SEFAZ
```

## 5. Boundaries obrigatórios

### 5.1 Outbound

- `FiscalSaleSnapshotMapper`
- `FiscalProfileResolver`
- `FiscalProductResolver`
- `FiscalCustomerResolver`
- `FiscalIssuanceApplication`
- `FiscalStatusProjection`

### 5.2 Inbound

- `FiscalDfeDistributionAdapter`
- `FiscalNsuCheckpointStore`
- `FiscalInboundDocumentProcessor`
- `FiscalSupplierResolver`
- `FiscalPurchaseSnapshotMapper`
- `FiscalInboundApplication`
- `FiscalInboundReconciliation`

### 5.3 Infra privada

- durable `FiscalSequenceStore`
- durable `FiscalIdempotencyStore`
- durable `FiscalOutboxStore`
- durable `FiscalArchiveStore`
- lifecycle/status projection
- `FiscalSignerAdapter`
- XML concrete adapters
- `FiscalGatewayAdapter`

## 6. Persistência prevista

Os nomes finais serão congelados no bloco de migration. A granularidade mínima é:

1. fiscal issuer/unit profile;
2. fiscal product binding;
3. fiscal document projection;
4. fiscal issuance/idempotency record;
5. fiscal sequence stream;
6. fiscal outbox;
7. fiscal archive metadata/reference;
8. inbound document;
9. inbound item;
10. DF-e NSU checkpoint;
11. manifestation/event ledger;
12. supplier canonical record, somente se não houver autoridade reaproveitável;
13. purchase order/receipt, somente se não houver autoridade reaproveitável;
14. product/insumo matching history;
15. fiscal receipt reconciliation.

Todas as tabelas devem possuir escopo tenant/unidade quando aplicável e constraints de unicidade/idempotência. Para autoridades fiscais dependentes de ambiente, `ExecutionScope.partition_key = tenant_id + unit_id + environment` é estrutural: homologação e produção devem coexistir sem colisão de identidade.

### 6.1 CURRENT pós-WP-031H certificado

- `FiscalSequenceStore`, `IdempotencyStore`, `FiscalOutboxStore` e `FiscalArchiveStore` possuem adapters SQLAlchemy duráveis.
- `FiscalIssuerProfileStoreSQLAlchemy` e `FiscalProductProfileStoreSQLAlchemy` resolvem perfis imutáveis e effective-dated.
- O Audit & Fix Pré-WP-031E tornou `environment` parte estrutural da identidade persistente de issuer e product profile e adicionou a migration evolutiva `0044_fiscal_profile_environment_partition_v1`.
- O Outbox SQLAlchemy deve manter equivalência semântica com `InMemoryFiscalOutboxStore`, inclusive validação estrita de `limit`, timezone de `available_at`, identidade SHA-256 e ordem de validação/transição.
- O outbound permanece fail-safe em `HOMOLOGATION` quando nenhum ambiente é injetado. A seleção final por Control Plane fiscal pertence ao wiring governado de WP-031I/J; não é autoridade do browser e não foi antecipada neste hardening.
- Gate `WP-031 Pre-E Audit & Fix Gate` run `35465047494`: SUCCESS no HEAD funcional `f2ed3f2f2701b1a62af3d8c61299311a167f660c`, com 1581 passed / 5 skipped / 102 warnings na regressão integral.
- O WP-031E adicionou contrato provider-neutral de distribuição DF-e, parser determinístico de XML NF-e modelo 55, Inbox e itens duráveis, checkpoint NSU monotônico e manifestação replay-safe.
- A migration aditiva `0045_fiscal_inbound_foundation_v1` materializa itens inbound e índices completos por `tenant_id + unit_id + environment`; o schema baseline passou a 91 tabelas.
- XML upload e DF-e da mesma chave convergem sem duplicidade; replays divergentes de chave, NSU ou manifestação falham fechados; documento e checkpoint DF-e são persistidos na mesma transação.
- Gate `WP-031E Inbound Fiscal Foundation` run `35485517752`: SUCCESS no HEAD funcional `0733a910c600819b3ae26b8ce7edb2883152a9c9`; matriz completa do SHA: 21/21 workflows SUCCESS; regressão local: 1590 passed / 5 skipped / 102 warnings.
- O WP-031F adicionou `SmartFiscalIntakeApplication`, captura preliminar durável, arquivo original atômico, boundary de extração estruturada e reconciliação determinística contra o documento oficial.
- A migration aditiva `0046_fiscal_smart_intake_v1` materializa a captura por `tenant_id + unit_id + environment`; o schema baseline passou a 92 tabelas.
- PDF, imagem e câmera permanecem evidência preliminar; DF-e/XML permanecem autoridade oficial. Nenhum fluxo do WP-031F movimenta estoque, cria procurement ou produz efeito financeiro.
- Gate `WP-031F Smart Fiscal Intake` run `35487571304`: SUCCESS no HEAD funcional `b3a5424d74497a55c96046585793d271e658887f`; matriz completa do SHA: 22/22 workflows SUCCESS; regressão local: 1601 passed / 5 skipped / 102 warnings.
- A certificação do WP-031F foi técnica interna e não antecipou provider/SEFAZ real, signer, certificado, homologação externa, precisão de OCR em produção, procurement, estoque ou financeiro.
- O WP-031G confirmou por discovery a ausência de autoridade materializada e criou uma única autoridade canônica de procurement, sem duplicar estoque, catálogo, fiscal ou financeiro.
- Fornecedor, pedido, aprovação, vínculo de produto, recebimento e custo de aquisição são duráveis e particionados por `tenant_id + unit_id + environment`.
- XML/DF-e fornece a verdade documental; a confirmação humana fornece a verdade física. Somente recebimento aceito em `production` movimenta o ledger canônico de estoque; homologação, divergência e rejeição não contaminam saldo operacional.
- A migration aditiva `0047_fiscal_procurement_integration_v1` elevou o schema baseline a 97 tabelas, com hash `a6a9ce9704ec3d62a6e32f71f2d54e4709fe4b24f3c1e18338d67dc38d43bb10`.
- Gate `WP-031G Procurement Integration` run `35510517704`: SUCCESS no HEAD funcional `040d26154d3eb344e7b81b070ad619d22ff42357`; matriz completa do SHA: 23/23 workflows SUCCESS; regressão: 1621 passed / 5 skipped / 102 warnings.
- A certificação é técnica interna. Efeitos financeiros/contábeis, signer, certificado, provider/SEFAZ real e homologação externa não foram antecipados.
- O WP-031H confirmou `core/pagamentos` como autoridade financeira canônica e a estendeu sem criar segundo ledger ou tratar contas a pagar como recebimento de venda.
- Recebimentos físicos autorizados em `production` criam obrigação de compra única; NF-e isolada, homologação, divergência e rejeição não criam efeito financeiro.
- Devolução e cancelamento geram ajustes append-only, preservam o valor original e alteram a versão da obrigação.
- Crédito tributário nasce somente de regra explícita com identidade, versão, vigência, CFOP, CST e alíquota; ausência de regra resulta em decisão `BLOQUEADO` com valor zero.
- Uma decisão tributária deixa de alimentar projeções quando a versão da obrigação muda, exigindo nova decisão após ajuste/devolução.
- A migration aditiva `0048_fiscal_financial_tax_bridge_v1` elevou o schema baseline a 100 tabelas, com hash `6724f5e6a6b558ac82f9f88e4c964978fb10b0a94eb81e75ee085a76ca6cb645`.
- Gate `WP-031H Financial Tax Bridge` run `35512559855`: SUCCESS no HEAD funcional `1cd054e4d0748faafeb781cb145d0f4824be2bad`; matriz completa do SHA: 24/24 workflows SUCCESS; regressão: 1614 passed / 5 skipped / 102 warnings.
- A certificação é técnica interna. Pagamento/liquidação automática, escrituração oficial, signer, certificado, provider/SEFAZ real e homologação externa não foram antecipados.
- WP-031I e WP-031J estão certificados internamente. WP-031J: HEAD `dab486acae6b8df70446089130a75773f271fc55`, gate `WP-031J Web UX Functional` run `35550921933` SUCCESS, matriz 26/26 workflows SUCCESS.
- O WP-031K reutilizou o Core canônico `core/gerente_ia` e adicionou `consultar_fiscal` como capacidade estritamente read-only sobre projeções determinísticas. A tool exige `GERENTE_IA_CONSULTAR` e `FISCAL_VISUALIZAR`, preserva tenant/unidade/ambiente, não lê XML/archive bruto nem Secret Store e marca recomendações como `execucao=nao_executada`.
- Gate `WP-031K Cognitive Fiscal` run `35553683984`: SUCCESS no HEAD funcional `8ee77732f7f1cba5da8403872217bd2ee2cad986`; regressão integral 1637 passed / 5 skipped / 102 warnings; matriz completa do SHA: 27/27 workflows SUCCESS.
- O WP-031L consolidou fitness contract de autoridade e regressão/channel parity sem introduzir nova autoridade. PDV e Delivery reutilizam Checkout V1; Salão/Garçom reutilizam Pagamentos V1; Marketplaces convergem em Pedido interno; o outbound fiscal continua nascendo de `venda.criada`.
- Gate `WP-031L Regression Channel Parity` run `35556451970`: SUCCESS no HEAD funcional `c990d1e92f87a6eea2110f4bc3141bff4321f6c8`; fitness 5 passed; canais 101 passed / 14 warnings; fiscal+cognitivo 109 passed / 5 warnings; pagamentos+estoque+segurança 150 passed / 56 warnings; regressão integral 1642 passed / 5 skipped / 102 warnings; Web Node 6/6; ESLint, TypeScript e Next production build verdes; matriz completa 28/28 workflows SUCCESS.
- WP-031 continua PENDING somente até o WP-031 Master Gate.

## 7. Regras de concorrência e idempotência

### Outbound

- uma `VendaFinanceira` gera no máximo uma intenção fiscal equivalente;
- replay de `venda.criada` não emite novamente;
- gateway pendente não é tratado como autorizado;
- retry/outbox não reserva nova numeração;
- numeração fiscal é atômica por tenant + unidade + ambiente + modelo + série.

### Inbound

- mesma chave NF-e não cria dois documentos;
- mesmo NSU não duplica ingestão;
- mesmo evento de manifestação é replay-safe;
- mesma confirmação de recebimento não movimenta estoque duas vezes;
- mesma obrigação de compra não cria duplicidade financeira.

## 8. Smart Fiscal Intake

Todas as fontes convergem para um único pipeline:

```text
DF-e oficial -----+
XML upload -------+
PDF --------------+--> Intake --> Normalização --> Reconciliação --> Recebimento
Imagem -----------+                  |
Câmera -----------+                  +--> XML/DF-e é autoridade fiscal
                                     +--> IA/OCR é interpretação preliminar
                                     +--> humano é autoridade do recebido físico
```

### Regra de autoridade

1. IA/OCR: extrai e sugere.
2. XML/DF-e/protocolo oficial: autoridade documental fiscal.
3. humano/recebimento: autoridade sobre quantidade e condição fisicamente recebidas.
4. serviço determinístico: decide efeitos fiscais, estoque e financeiro.

Nunca sobrescrever divergência silenciosamente.

## 9. Procurement e estoque

Fluxo alvo:

```text
Pedido de compra (quando aplicável)
    -> NF-e/DF-e
    -> conferência
    -> recebimento físico
    -> three-way match
    -> entrada idempotente em estoque
    -> atualização governada de custo
    -> obrigação financeira
```

Three-way match deve detectar quantidade, preço, produto, frete, desconto e total divergentes.

NF-e recebida não equivale a estoque recebido e não equivale a pagamento.

## 10. Financeiro

Autoridades permanecem separadas:

- Fiscal: documento e evento fiscal.
- Procurement: aquisição e recebimento.
- Estoque: saldo/movimento.
- Financeiro: obrigação e pagamento.

Créditos tributários devem nascer de decisão determinística versionada (`CreditEligibilityDecision`), nunca de regra genérica "imposto da compra = crédito".

## 11. Segurança

### RBAC target

Os identificadores finais devem ser adicionados à autoridade `Permissao`, sem sistema paralelo. Escopo mínimo:

- fiscal.visualizar
- fiscal.emitir
- fiscal.cancelar
- fiscal.inutilizar
- fiscal.manifestar
- fiscal.configurar
- fiscal.certificado
- fiscal.compras.visualizar
- fiscal.compras.receber
- fiscal.archive.visualizar

### Step-up

Obrigatório para configuração fiscal sensível, certificado, provider/credenciais, ambiente, cancelamento/inutilização administrativa e demais mutações classificadas como sensíveis.

### Segredos

PFX, senha, CSC, token, API key e private key nunca podem aparecer em frontend, repo, fixtures, logs, respostas HTTP ou telemetria.

## 12. APIs/Web target

Backoffice funcional pré-Premium:

- visão fiscal;
- documentos emitidos;
- documentos recebidos;
- Fiscal Inbox;
- compras/recebimentos;
- manifestação;
- configuração fiscal;
- certificados/referências;
- produtos com pendência fiscal;
- contingência/rejeições;
- cancelamento/inutilização;
- archive/reconciliação.

PDV e canais operacionais recebem somente projeção de estado necessária à operação.

## 13. Eventos principais

### Consumidos

- `venda.criada`
- eventos de pedido/pagamento necessários para construir snapshot
- eventos de recebimento/procurement futuros

### Produzidos

Naming final deverá seguir padrão de eventos existente. Semântica mínima:

- fiscal.documento.criado
- fiscal.documento.autorizado
- fiscal.documento.rejeitado
- fiscal.documento.pendente
- fiscal.documento.cancelado
- fiscal.contingencia.ativada
- fiscal.entrada.detectada
- fiscal.entrada.reconciliada
- fiscal.manifestacao.registrada
- fiscal.recebimento.confirmado
- fiscal.divergencia.detectada

## 14. Failure modes

Falhar fechado em:

- ausência de perfil fiscal;
- produto sem classificação necessária;
- certificado ausente/expirado;
- segredo indisponível;
- cross-tenant/cross-unit;
- schema/XML inválido;
- chave/protocolo incompatível;
- resposta de gateway com identidade divergente;
- regra tributária ausente/ambígua;
- readiness abaixo do mínimo;
- NSU/checkpoint inconsistente;
- replay com conteúdo divergente;
- tentativa de movimento duplicado no estoque.

Indisponibilidade externa deve ir para estado explícito/outbox/contingência; nunca converter indisponibilidade em sucesso.

## 15. Homologação e readiness

Estados internos e externos permanecem distintos.

- IMPLEMENTED/CERTIFIED_INTERNAL não significa homologação SEFAZ/provider.
- HOMOLOGATION_READY exige evidência do ambiente correspondente.
- PRODUCTION_APPROVED exige aprovação/evidência explícita.

Nenhuma UF, município ou provider será marcado como homologado sem evidência real.

## 16. Plano sequencial congelado

1. WP-031A — Discovery + Authority Freeze — este documento.
2. WP-031B — Fiscal Persistence Foundation.
3. WP-031C — Outbound Bridge.
4. WP-031D — Perfil / Produto Fiscal.
5. WP-031E — Inbound Fiscal Foundation — CONCLUÍDO/CERTIFICADO.
6. WP-031F — Smart Fiscal Intake — CONCLUÍDO/CERTIFICADO.
7. WP-031G — Procurement Integration — CONCLUÍDO/CERTIFICADO.
8. WP-031H — Financial / Tax Bridge — CONCLUÍDO/CERTIFICADO.
9. WP-031I — Signer + Gateway.
10. WP-031J — Web / UX funcional.
11. WP-031K — Cognitive Fiscal — CONCLUÍDO/CERTIFICADO.
12. WP-031L — Regression / Channel Parity — CONCLUÍDO/CERTIFICADO.
13. WP-031 Master Gate.
14. Visual Premium final.

Nenhum bloco seguinte é autorizado com falha aberta no bloco anterior.

## 17. Gate WP-031A

WP-031A é considerado fechado quando:

- baseline fiscal V1 congelado e documentado;
- autoridades Kordena mapeadas;
- lacunas outbound/inbound/procurement explicitadas;
- IA/OCR classificada corretamente como interpretação;
- estoque, financeiro, catálogo, RBAC, step-up e Secret Store preservados;
- nenhuma segunda autoridade criada;
- sequência Fiscal -> Premium reconciliada na documentação;
- PR permanece OPEN/DRAFT;
- CI existente do HEAD de entrada permanece verde.

**Estado ao criar este documento:** critérios arquiteturais satisfeitos; pendente somente a reconciliação documental versionada e execução dos gates do novo HEAD.
