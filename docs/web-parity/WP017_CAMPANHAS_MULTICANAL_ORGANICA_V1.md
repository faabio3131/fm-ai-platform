# WP-017 â€” CONCLUSÃƒO FUNCIONAL DA CENTRAL DE CAMPANHAS MULTICANAL ORGÃ‚NICA V1

**Data:** 04/10/2026
**Status:** EM CERTIFICAÃ‡ÃƒO â€” implementaÃ§Ã£o concluÃ­da na branch, gates finais em execuÃ§Ã£o
**Branch:** `fix/wp017-campanhas-organicas-multicanal`
**Base:** `staging/kordena-premium@863918c8b1c8bc27bad839252e02c6c6890b82b7`
**ClassificaÃ§Ã£o:** conclusÃ£o de lacuna funcional do WP-017; nÃ£o Ã© feature nova.

## 1. DecisÃ£o de produto

A V1 do Kordena mantÃ©m **marketing orgÃ¢nico com IA e aprovaÃ§Ã£o humana** nos trÃªs destinos previstos:

- **WhatsApp Business:** campanhas diretas de relacionamento/CRM para destinatÃ¡rios com canal disponÃ­vel e consentimento vigente.
- **Facebook Page:** publicaÃ§Ã£o orgÃ¢nica na pÃ¡gina configurada pelo tenant/unidade.
- **Instagram Business:** publicaÃ§Ã£o orgÃ¢nica com imagem HTTPS e legenda na conta configurada pelo tenant/unidade.

**Meta Ã© o provedor de integraÃ§Ã£o**, nÃ£o um quarto canal selecionÃ¡vel na Central de Campanhas.

Ficam explicitamente **fora da V1**:

- Meta Ads;
- Facebook Ads;
- Instagram Ads;
- orÃ§amento de mÃ­dia;
- CPC, CPM, ROAS;
- pÃºblicos de mÃ­dia paga;
- impulsionamento/trÃ¡fego pago.

## 2. Lacuna encerrada

A migraÃ§Ã£o Web original do WP-017 preservou apenas o dispatcher legado de WhatsApp, embora a arquitetura de produto e a camada de integraÃ§Ãµes jÃ¡ possuÃ­ssem Facebook e Instagram.

Esta conclusÃ£o conecta as capacidades jÃ¡ existentes do `MetaAdapter` Ã  Central de Campanhas sem criar segunda autoridade de campanhas, CRM, consentimentos ou integraÃ§Ãµes.

## 3. Arquitetura final da V1

```text
Central de Campanhas
        |
        v
Lifecycle canÃ´nico do WP-017
rascunho -> submissÃ£o -> aprovaÃ§Ã£o humana -> publicÃ¡vel -> efeito externo
        |
        +-----------------------+-----------------------+
        |                       |                       |
        v                       v                       v
WhatsApp Business          Facebook Page         Instagram Business
CRM + consentimento        orgÃ¢nico              orgÃ¢nico + mÃ­dia
        |                       |                       |
        +-----------------------+-----------------------+
                                |
                                v
                         Meta / MetaAdapter
                                |
                                v
                    Central de IntegraÃ§Ãµes
                    tenant + unidade + secrets
```

## 4. Invariantes preservados

- campanha nova continua exigindo aprovaÃ§Ã£o humana;
- step-up continua exigido nas operaÃ§Ãµes sensÃ­veis jÃ¡ protegidas;
- tenant e unidade permanecem derivados da sessÃ£o assinada;
- credenciais Meta nÃ£o ficam no cÃ³digo nem na campanha;
- configuraÃ§Ã£o e homologaÃ§Ã£o continuam pertencendo Ã  Central de IntegraÃ§Ãµes;
- ausÃªncia, desativaÃ§Ã£o, credencial invÃ¡lida ou falta de homologaÃ§Ã£o falha fechado;
- WhatsApp continua revalidando consentimento antes do efeito externo;
- Facebook/Instagram nÃ£o reutilizam audiÃªncia CRM porque sÃ£o publicaÃ§Ãµes de conta, nÃ£o mensagens a destinatÃ¡rios;
- mÃ­dia do Instagram faz parte do aggregate/fingerprint aprovado;
- retries nÃ£o podem duplicar efeitos externos.

## 5. IdempotÃªncia de publicaÃ§Ã£o social

Facebook e Instagram usam ledger durÃ¡vel baseado na Outbox V1 antes da chamada Ã  Meta.

Estados relevantes:

- reserva local confirmada antes do POST externo;
- sucesso registra o ID externo retornado pela Meta;
- replay apÃ³s sucesso retorna o mesmo ID sem republicar;
- resultado externo incerto bloqueia retry automÃ¡tico e exige reconciliaÃ§Ã£o, evitando post duplicado.

O WhatsApp preserva o mecanismo at-most-once jÃ¡ existente no CRM.

## 6. PersistÃªncia

Migration adicionada:

`0068_campaign_organic_media_v1`

AlteraÃ§Ã£o aditiva:

`crm_rascunhos_campanha_v1.midia_url TEXT NULL`

A coluna Ã© opcional para preservar campanhas legadas. Quando nÃ£o existe mÃ­dia, o fingerprint legado nÃ£o recebe campo adicional.

## 7. UX Web

A Central apresenta somente destinos funcionais:

- WhatsApp;
- Facebook;
- Instagram.

Comportamento:

- WhatsApp mostra audiÃªncia e consentimento;
- Facebook mostra publicaÃ§Ã£o orgÃ¢nica na Page configurada;
- Instagram exige URL HTTPS de imagem e legenda;
- nÃ£o existem campos de orÃ§amento, CPC, CPM, ROAS ou mÃ­dia paga;
- erros de configuraÃ§Ã£o Meta orientam o usuÃ¡rio a concluir IntegraÃ§Ãµes;
- resultado externo incerto explica que o replay automÃ¡tico foi bloqueado para impedir duplicaÃ§Ã£o.

## 8. EvidÃªncias executadas atÃ© este checkpoint

Backend direcionado apÃ³s implementaÃ§Ã£o social:

```text
19 passed
```

Inclui:

- Facebook/Instagram sem audiÃªncia CRM;
- WhatsApp mantendo audiÃªncia obrigatÃ³ria;
- mÃ­dia Instagram alterando fingerprint;
- publicaÃ§Ã£o Facebook;
- publicaÃ§Ã£o Instagram;
- replay idempotente sem segundo POST;
- timeout/resultado incerto bloqueando retry cego;
- contrato HTTP;
- migration manifest.

Teste estrutural Web WP-017:

```text
4 passed
```

Ruff dos arquivos Python alterados:

```text
All checks passed!
```

## 9. Gate final ainda necessÃ¡rio

Antes de marcar este documento como **CERTIFICADO**, concluir e registrar:

- regressÃ£o Python completa;
- ESLint;
- TypeScript;
- Next build;
- `git diff --check`;
- commit/SHA final;
- CI do HEAD final da PR.

## 10. Isolamento de escopo

A PR #190 permanece independente e nÃ£o Ã© usada para esta correÃ§Ã£o.

Esta conclusÃ£o deve seguir em PR prÃ³pria contra `staging/kordena-premium`.

**Nenhum merge Ã© autorizado por este documento.**
