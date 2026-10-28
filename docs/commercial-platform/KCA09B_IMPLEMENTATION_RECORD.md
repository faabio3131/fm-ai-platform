# KCA-09B — Implementation Record

## Escopo
Configuração multi-provider e contas recebedoras da FM Commercial Platform, executada antes do KCA-10.

## Candidate funcional
- SHA: `b38f20b0c7520e39203076a07923c76767ffb970`.
- Base: `staging/kordena-premium`.
- KCA-G9 previamente certificado.
- KCA-10 não iniciado.

## Persistência
- Migration: `0057_commercial_billing_config_v1`.
- Novas tabelas:
  - `fm_billing_provider_accounts_v1`
  - `fm_billing_routing_policies_v1`
- Schema baseline: **127 tabelas**.
- Schema SHA-256: `dfa71718df03907d1cf44cdb7f54ce774d7b05395b4a9ef20885d90951e88c55`.
- Manifest fingerprint da migration 0057: `3d255142b5aebc4f6e52d6fe0c818a5e4b34ffa8fa6324ceee2ecf99ca886eb6`.

## Provider Accounts
Implementado cadastro configurável com:
- `provider_account_id`;
- `provider_code` aberto/provider-neutral;
- `display_name`;
- `legal_entity_ref` opcional;
- ambiente `SANDBOX` / `PRODUCTION`;
- status `DRAFT`, `VALIDATING`, `ACTIVE`, `SUSPENDED`, `DISABLED`;
- referência de credencial opcional em DRAFT;
- métodos de pagamento suportados;
- capacidades de recorrência e webhooks;
- prioridade;
- último teste de conexão/status;
- optimistic concurrency/version;
- timestamps/correlation/audit.

## Credential onboarding
- Conta pode existir em DRAFT sem credencial.
- Credencial pode ser cadastrada/rotacionada posteriormente pela administração.
- Valor digitado é tratado como `SecretStr` no boundary HTTP.
- Backend reutiliza `EncryptedSQLAlchemySecretStore`.
- Valor em claro nunca é persistido na configuração comercial.
- Configuração mantém somente referência `vault:*`/secret reference.
- Vault é cifrado com chave mestra de infraestrutura.
- Referências `vault:*` são validadas contra tenant/unidade administrativos.
- Rotação força status VALIDATING e invalida teste anterior.
- API não devolve valor nem referência da credencial.

## Adapter Registry
- Registry runtime provider-neutral.
- Nenhuma enumeração fechada de provider.
- Nenhum provider financeiro real conectado.
- Nenhum SDK de Mercado Pago, PagBank, Stripe, Cakto ou outro provider concreto no domínio.
- `test_connection` adicionado ao contrato do BillingProvider.
- Teste de conexão não executa cobrança.
- Resultado técnico é sanitizado e não pode carregar segredo livremente.

## Routing Policy
Implementado roteamento por:
- produto;
- método de pagamento;
- ambiente;
- conta primária;
- fallbacks ordenados;
- requisito opcional de recorrência;
- requisito opcional de webhooks;
- ativo/inativo;
- versionamento/concorrência otimista.

Regras:
- policy só referencia contas ACTIVE;
- ambiente deve coincidir;
- método deve ser suportado;
- recurring/webhook capabilities são exigidas quando configuradas;
- primary/fallback não podem duplicar;
- ausência de rota válida falha fechado;
- conta suspensa/incompatível é retirada da decisão;
- fallback é somente ordem autorizada;
- roteamento NÃO dispara cobrança e NÃO tenta múltiplos providers automaticamente.

## Administração / FM Control Center
- API administrativa pronta para futura superfície do FM Control Center.
- Mesma barreira administrativa/step-up do Commercial Platform.
- Gerente sem autoridade administrativa continua negado.
- Frontend futuro será cliente da FM Commercial Platform, não autoridade financeira.

## Separação de bounded contexts
- Billing SaaS da FM permanece separado dos pagamentos operacionais dos clientes Kordena.
- Cakto permanece fora do BillingProvider central; eventual integração é canal de venda/distribuição.
- Nenhum webhook inbox/reconciliation do KCA-10 foi implementado.

## Evidência de testes — candidate funcional
- Migration manifest: PASS.
- Schema baseline: PASS.
- Ruff/mypy KCA: PASS.
- KCA targeted: **161 passed, 2 warnings**.
- Full Python: **1762 passed, 5 skipped, 102 warnings**.
- Web Node: **14 tests, 14 pass, 0 fail**.
- Web ESLint: PASS.
- Web TypeScript: PASS.
- Next production build: PASS.
- Diff whitespace: PASS.
- GitHub Actions: **13/13 workflows SUCCESS**.

## Governança
- PR #126 permanece OPEN/DRAFT.
- Nenhum merge.
- Nenhum deploy público.
- `main` não alterada.
- Nenhuma conta financeira real criada.
- Nenhuma credencial real cadastrada.
- Nenhum provider financeiro real integrado.
- Nenhuma cobrança real.
- Nenhum webhook financeiro real.
- KCA-10 não iniciado.

## Gate
**KCA-G9B: PASS**

## Próxima fronteira
KCA-10 — Webhook Inbox + Reconciliation permanece bloqueado até a recertificação do HEAD documental deste gate.
