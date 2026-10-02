# WP-017 — Decisão de Escopo V1: Campanhas Orgânicas

**Status:** CONCLUÍDO / CERTIFIED PARA A V1
**Data da decisão:** 02/10/2026
**Produto:** Kordena
**Work Package:** WP-017 — Marketing / Resgate / Campanhas

## 1. Decisão executiva

Para a **V1 comercial do Kordena**, o escopo de Marketing / Campanhas fica deliberadamente limitado a **campanhas orgânicas/diretas, sem compra de mídia**.

Para fins de escopo da V1, campanha orgânica significa ação de marketing executada sem orçamento de tráfego pago, usando base própria/CRM, consentimento e os canais efetivamente suportados pelo produto. No CURRENT certificado do WP-017, o canal externo comprovado é o fluxo comercial de WhatsApp integrado ao CRM.

## 2. Escopo V1 considerado concluído

O WP-017 V1 cobre e já possui certificação para:

- criação e edição de rascunho;
- definição governada de audiência;
- uso da base própria de clientes/CRM;
- validação de consentimento antes do despacho;
- submissão para aprovação;
- aprovação humana;
- publicação/liberação humana;
- despacho explícito e governado;
- proteção idempotente/replay-safe do efeito externo;
- histórico e auditoria;
- integração CRM → Campanhas;
- integração do Gerente IA somente até a criação de rascunho;
- isolamento tenant/unidade, RBAC e step-up quando aplicável.

A implementação Web first-class está em `/admin/campanhas`, com API `/v1/campanhas`.

## 3. Fora do escopo da V1

Não é requisito da V1 e **não constitui pendência do WP-017**:

- Meta Ads / Facebook Ads;
- Instagram Ads;
- Google Ads;
- compra automatizada de mídia;
- orçamento de campanha paga;
- conjuntos/grupos de anúncios;
- bidding;
- CPC, CPM, CPA ou ROAS de mídia;
- gestão de tráfego pago;
- otimização automática de verba;
- publicação de anúncios patrocinados;
- integração com contas de anúncios para mídia paga.

Essas capacidades podem ser avaliadas em versão posterior e não devem reabrir o WP-017 V1.

## 4. Observação sobre redes sociais orgânicas

A decisão desta V1 é **não exigir mídia paga**. Publicação orgânica em rede social específica somente poderá ser declarada como funcionalidade suportada quando existir integração e evidência técnica próprias. A ausência dessa integração não impede o fechamento do WP-017 V1, pois a autoridade funcional certificada da V1 é a campanha orgânica/direta baseada em CRM e canais efetivamente suportados.

## 5. Evidência de certificação existente

A decisão de escopo não altera nem substitui a certificação técnica já concluída:

- PR #174 — Central Web `/admin/campanhas` + API `/v1/campanhas`;
- HEAD certificado: `e0837d7651c942da69cbb4a7e6666144340d4a5e`;
- workflow `Kordena WP017 Campaign Web Parity`, run `36918120350` — SUCCESS;
- 31 testes dirigidos PASS;
- regressão Python completa: 1862 PASS / 5 SKIP / 0 FAIL;
- TypeScript, Web structural tests, Next production build e diff check PASS;
- 24/24 workflows SUCCESS no commit certificado;
- pós-merge Vercel e Railway verdes.

## 6. Estado final V1

```text
WP-017_V1_SCOPE = ORGANIC_DIRECT_CAMPAIGNS
PAID_MEDIA_V1 = OUT_OF_SCOPE
WP-017_V1 = CERTIFIED
WP-017_V1_PENDING = NONE
```

Esta decisão é normativa para auditorias, inventários, cronogramas e gates da V1. Mídia paga não deve ser reportada como gap, pendência ou bloqueio da V1 do Kordena.
