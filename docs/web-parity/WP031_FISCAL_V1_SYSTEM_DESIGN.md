# WP-031 — Fiscal V1 Complete — System Design & Authority Map

**Status:** WP-031A→D implementados/certificados; Audit & Fix Pré-WP-031E CERTIFICADO; WP-031E não iniciado
**Date:** 18/09/2026
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

Existe a permissão `compra.aprovar` no RBAC, mas a auditoria do CURRENT não localizou autoridade canônica materializada para pedido de compra, fornecedor, recebimento fiscal ou DF-e.

**Decisão:** antes de criar essas autoridades, WP-031G deve executar uma segunda descoberta dirigida no tree final. Se a autoridade continuar ausente, será criada uma única autoridade canônica de procurement, integrada ao estoque/financeiro existentes.

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

### 6.1 CURRENT pós-WP-031D / Audit & Fix Pré-E certificado

- `FiscalSequenceStore`, `IdempotencyStore`, `FiscalOutboxStore` e `FiscalArchiveStore` possuem adapters SQLAlchemy duráveis.
- `FiscalIssuerProfileStoreSQLAlchemy` e `FiscalProductProfileStoreSQLAlchemy` resolvem perfis imutáveis e effective-dated.
- O Audit & Fix Pré-WP-031E tornou `environment` parte estrutural da identidade persistente de issuer e product profile e adicionou a migration evolutiva `0044_fiscal_profile_environment_partition_v1`.
- O Outbox SQLAlchemy deve manter equivalência semântica com `InMemoryFiscalOutboxStore`, inclusive validação estrita de `limit`, timezone de `available_at`, identidade SHA-256 e ordem de validação/transição.
- O outbound permanece fail-safe em `HOMOLOGATION` quando nenhum ambiente é injetado. A seleção final por Control Plane fiscal pertence ao wiring governado de WP-031I/J; não é autoridade do browser e não foi antecipada neste hardening.
- Gate `WP-031 Pre-E Audit & Fix Gate` run `35465047494`: SUCCESS no HEAD funcional `f2ed3f2f2701b1a62af3d8c61299311a167f660c`, com 1581 passed / 5 skipped / 102 warnings na regressão integral.
- WP-031E continua PENDING / NÃO INICIADO e depende de autorização explícita do proprietário.

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
5. WP-031E — Inbound Fiscal Foundation.
6. WP-031F — Smart Fiscal Intake.
7. WP-031G — Procurement Integration.
8. WP-031H — Financial / Tax Bridge.
9. WP-031I — Signer + Gateway.
10. WP-031J — Web / UX funcional.
11. WP-031K — Cognitive Fiscal.
12. WP-031L — Regression / Channel Parity.
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
