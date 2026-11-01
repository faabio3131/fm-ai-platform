# Kordena V1 — CURRENT de produção e checkpoint de release — 01/11/2026

> **Autoridade operacional atualizada em 01/11/2026.** Este registro complementa, sem reescrever retroativamente, o Cronograma Mestre V1 Comercial v2.0 e o KCA Execution Tracker. Os SHAs e as evidências abaixo foram verificados no GitHub e diretamente na Contabo por SSH via Desktop Commander. Não usar snapshots históricos de Railway/Vercel ou do CURRENT de setembro como estado atual.

## 1. Fonte de verdade e release

| Item | CURRENT certificado |
|---|---|
| Repositório | `faabio3131/fm-ai-platform` |
| Branch de deploy de produção | `production` |
| SHA implantado e validado | `53013ae44449936a383517211a7d21b53932b2fd` |
| PR de promoção à produção | [#235](https://github.com/faabio3131/fm-ai-platform/pull/235), MERGED |
| PR original de construção | [#234](https://github.com/faabio3131/fm-ai-platform/pull/234), MERGED em `staging/kordena-premium` |
| Staging usada na construção | `ebf8cdb9420d3b36af59d19f3281d95cbb4746ba` (snapshot de 01/11) |
| Base produtiva preservada | `6808a0352fc8de298762bd1316503b3a0e135720` (inclui Evolution WhatsApp #233) |
| Ambiente público | Contabo `vmi3692211` / `13.140.234.22` |
| Frontend | `https://app.kordenaia.com.br` |
| API | `https://api.kordenaia.com.br` |

**Regra crítica de branches:** `production`, e **não** `main` ou `staging/kordena-premium`, é a única ref consumida pelo deploy automático atual. A staging e a production possuíam histórias divergentes em 01/11 (production com 1.151 commits não presentes em staging). NÃO mesclar staging diretamente em production nem sobrescrever a árvore da produção. Fazer reconciliação por ancestralidade e levar somente mudanças selecionadas sobre a cabeça exata de production, com PR e CI exact-HEAD.

## 2. Mecanismo atual de deploy

- Usuário remoto de operação: `fmadmin`; acesso SSH do PC autorizado pelo Desktop Commander com chave `fm_contabo2` carregada em `ssh-agent`. Não colocar chave, senha, tokens ou `.env` em commits ou logs.
- Cron de `fmadmin`: `*/5 * * * * flock -n /tmp/kordena-deploy.lock /opt/fm/kordena/deploy.sh >> /opt/fm/kordena/deploy.log 2>&1`. `cron` estava `active` em 01/11.
- Script: `/opt/fm/kordena/deploy.sh`; ref padrão `production`; estado `/opt/fm/kordena/.deployed`; supressão de tentativa falha `/opt/fm/kordena/.failed-sha`.
- Antes do build: verifica ancestralidade/alterações destrutivas, faz dump de PostgreSQL e confere SHA-256. Em falha, o script possui rotina de rollback para imagens anteriores, restaurando banco se migração foi aplicada/tentada, com alarme se a restauração falhar. **A existência desse mecanismo não substitui ensaio/validação de restauração.**
- Após build API + Web, verifica migrations, sobe containers, executa saúde local API `127.0.0.1:8100/healthz` e Web `127.0.0.1:3100/`; só então escreve `.deployed`.
- **Merge em `production` é um gatilho de deploy real, não um merge meramente documental.** Exige autorização de produção, CI exata, backup, rollback e acompanhamento. Mudanças apenas em documentação também alteram o SHA e podem provocar rebuild do cron.

## 3. Recuperação do upsell/cross-sell da Atendente IA

**Origem da lacuna:** o commit histórico `41ef48ac121a024db3e59cad5b32145c62aedd5c` (27/07/2026) continha prompts de cross-selling no `app.py` legado Streamlit, com exemplos fixos. O código legado não foi apagado, mas a capacidade não estava conectada ao fluxo modular atual.

**Escopo entregue nas PRs #234/#235:**
- Recomendações de complementos (bebidas não alcoólicas, acompanhamentos e sobremesas) com produtos ativos e preços provenientes do catálogo canônico da unidade;
- upsell conservador de variante superior do mesmo produto, substituindo em vez de duplicar item;
- máximo de uma oferta por pedido no fluxo implementado; aceite/recusa explícitos em texto ou áudio transcrito via canal WhatsApp Evolution;
- persistência da oferta no estado de conversa e reconsulta do catálogo antes do aceite; defesa de tenant/unidade, disponibilidade e preço alterado;
- confirmação final do cliente e fingerprint do carrinho recalculado quando a oferta é aceita; a IA não autoriza cobrança, criação de itens fictícios nem inserção automática sem aceite;
- proteção de não sugerir álcool automaticamente sem verificação de idade.

**Evidência de código:** na candidata gerada sobre production, 89 testes direcionados (Atendente + Evolution) PASS, Ruff PASS e mypy PASS. Na PR #235, **9 checks CI exact-HEAD SUCCESS** (entre eles Assistente F4, E2E integrado, backend, frontend, fiscal A–L e paridade, readiness e Visual Premium). Não reconstruir a funcionalidade nem substituir o runtime modular pelo `app.py` legado.

**Limite importante:** implantação e smoke HTTP **não são prova de homologação por conversa real** com cliente/tenant autorizado. Essa homologação externa permanece pendente; não declarar `WHATSAPP_UPSELL_EXTERNAL_HOMOLOGATED=PASS` sem evidência real e consentimento.

## 4. Evidências do deploy Contabo (01/11/2026)

- `2026-11-01T21:20:02Z == DEPLOY inicio 6808a03->53013ae`.
- Backup pré-deploy criado e com hash verificado: `/opt/fm/backups/kordena-diario/kordena-predeploy-20261101-222004.dump`.
- Build de API e Web concluídos, incluindo Next.js 16.4.3; migrations: `Schema comercial V1 ja esta atualizado.`
- `2026-11-01T21:26:45Z == DEPLOY OK 53013ae`.
- `.deployed` igual a `53013ae44449936a383517211a7d21b53932b2fd`; `.failed-sha` ausente; `deploy.sh --check` retornou `sem mudancas (53013ae)`.
- Containers `kordena-api-1` e `kordena-web-1` recriados em `2026-11-01T21:26:22Z`; `kordena-db-1` `healthy`.
- Smoke local API/Web HTTP 200. Smoke externo: `https://app.kordenaia.com.br/login` HTTP 200, `https://api.kordenaia.com.br/healthz` HTTP 200; `https://app.kordenaia.com.br/backend/healthz` respondeu `{"ok":true,"backend":"postgresql","detail":"database_ready"}`.
- A infraestrutura atual é **Contabo**, não Railway/Render/Vercel. Registros antigos desses providers permanecem como histórico, não como instrução operacional presente.
- DNS de `kordenaia.com.br` e `www.kordenaia.com.br` aponta para a Contabo e redireciona por HTTPS 302 para `https://app.kordenaia.com.br`; `www` CNAME aponta para a raiz; registros do Brevo preservados. Esta verificação é separada do deploy da função.

## 5. Pendências classificadas — não reabrir o que passou

| Item | Estado em 01/11 | Evidência ou próximo gate |
|---|---|---|
| Implementação upsell/cross-sell | **PASS** | PRs #234 e #235 |
| Testes automatizados e CI de release | **PASS** | 89 testes locais; 9 checks #235 |
| Deploy da release em produção | **PASS** | `.deployed` e smoke HTTP no SHA `53013ae` |
| Homologação real via Evolution WhatsApp | **PENDING_EXTERNAL_EVIDENCE** | Tenant/unidade autorizados; conversa real com sugestão, aceite/recusa, atualização do carrinho, confirmação final, não duplicidade e logs/auditoria sem dados sensíveis |
| Texto comercial nas páginas Kordena/FM Tecnologia | **REVIEW_PENDING** | Conferir copy real em cada origem. Não prometer função como homologada externamente antes do teste; não assumir que a página externa foi alterada |
| Signup/trial público, billing real, legal e demais gates do Cronograma Mestre | **MANTER ESTADO INDIVIDUAL DO GATE** | Deploy de #235 não implica GO comercial geral nem liberação de cobrança/trial público |
| Kordena → NFCore | **DEFERRED_BY_DESIGN** | Cronograma específico posterior |

## 6. Comandos seguros de continuidade (somente leitura)

```bash
git ls-remote https://github.com/faabio3131/fm-ai-platform.git refs/heads/production
ssh fmadmin@13.140.234.22 'cat /opt/fm/kordena/.deployed'
ssh fmadmin@13.140.234.22 '/opt/fm/kordena/deploy.sh --check'
ssh fmadmin@13.140.234.22 'tail -n 60 /opt/fm/kordena/deploy.log'
ssh fmadmin@13.140.234.22 'test -f /opt/fm/kordena/.failed-sha && cat /opt/fm/kordena/.failed-sha || echo none'
curl -fsS https://api.kordenaia.com.br/healthz
```

Nunca rodar o `deploy.sh` sem `--check` durante uma auditoria somente leitura. Não confundir CI aprovada com canal externo homologado; não refazer PRs #234/#235.
