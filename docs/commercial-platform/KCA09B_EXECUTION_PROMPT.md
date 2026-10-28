# PROMPT MESTRE — KCA-09B

## Multi-Provider Configuration & Receiving Accounts

### Missão
Implementar, antes do KCA-10, a camada configurável de contas recebedoras da FM Commercial Platform.

### Dependência
- KCA-09 / KCA-G9: PASS.
- Não iniciar KCA-10 enquanto KCA-G9B não estiver PASS.

### Objetivos
1. Permitir múltiplas contas de recebimento configuráveis.
2. Não hardcodar provider financeiro.
3. Permitir ambientes SANDBOX e PRODUCTION.
4. Permitir métodos de pagamento por conta.
5. Permitir capacidades de recorrência e webhooks por conta.
6. Permitir conta DRAFT sem credencial e onboarding posterior pelo FM Control Center.
7. Persistir somente referências de segredo, nunca credenciais em claro.
8. Reutilizar o Secret Vault cifrado existente para converter credenciais digitadas em referências `vault:*`.
9. Criar Provider Adapter Registry em runtime.
10. Criar teste de conexão não financeiro.
11. Criar políticas de roteamento com conta primária e fallbacks ordenados.
12. Permitir que routing policies exijam recorrência e/ou webhooks.
13. Resolver rota de pagamento de forma determinística e fail-closed.
14. Proteger administração com RBAC + step-up existente.
15. Auditar criação, alteração, credencial, teste, ativação e roteamento.
16. Expor contrato administrativo que o FM Control Center poderá consumir futuramente.
17. Manter billing SaaS da FM separado dos pagamentos operacionais do Kordena.

### Fora de escopo
- provider financeiro real;
- credenciais reais;
- cobrança real;
- webhook financeiro real;
- KCA-10 Webhook Inbox + Reconciliation;
- FM Control Center visual;
- failover que tente cobrança automaticamente em múltiplos providers;
- Cakto como BillingProvider.

### Modelo mínimo — Provider Account
- provider_account_id
- provider_code
- display_name
- legal_entity_ref opcional
- environment
- status
- credential_secret_reference
- supported_payment_methods
- supports_recurring
- supports_webhooks
- priority
- last_tested_at
- last_test_status
- version
- created_at
- updated_at

Status:
DRAFT → VALIDATING → ACTIVE → SUSPENDED | DISABLED

### Modelo mínimo — Routing Policy
- routing_policy_id
- product_code
- payment_method
- environment
- primary_provider_account_id
- fallback_provider_account_ids
- active
- version
- created_at
- updated_at

### Regras
- provider_code é configurável, não uma enumeração fechada.
- conta pode permanecer DRAFT sem credencial até a empresa possuir conta/credenciais reais.
- credencial digitada pela administração deve ser cifrada no Secret Vault; a configuração persiste somente `vault:*`/secret reference.
- referências `vault:*` devem pertencer ao mesmo tenant/unidade administrativo.
- conta PRODUCTION não pode ser ativada sem teste de conexão PASS.
- policy só pode apontar para contas ACTIVE, compatíveis com ambiente e método.
- primary/fallback não podem se repetir.
- rota sem policy válida falha fechado.
- roteamento não executa cobrança; apenas seleciona uma ordem autorizada.
- nenhum segredo em logs, eventos, API ou banco.
- alterações administrativas exigem a barreira administrativa já existente.

### Persistência
Criar migration aditiva no próximo slot livre real. Se o CURRENT terminar em 0056, usar 0057; não assumir sem reconciliar.
Atualizar runner, manifest, schema baseline e testes de sequência.

### Testes obrigatórios
- múltiplas contas;
- provider_code livre/configurável;
- sandbox/prod;
- secret reference;
- teste de conexão PASS/FAIL;
- ativação somente após PASS;
- métodos suportados;
- recurring/webhook capabilities;
- primary + fallbacks;
- incompatibilidade de ambiente;
- método não suportado;
- conta suspensa/desabilitada;
- route fail-closed;
- optimistic concurrency;
- idempotência;
- RBAC/step-up;
- nenhum segredo exposto;
- nenhuma dependência de provider concreto;
- Billing FM separado de pagamentos operacionais;
- KCA-10 não antecipado.

### Gate KCA-G9B
PASS somente com migration/schema/manifest verdes, testes direcionados verdes, regressão completa verde, Web verde, CI obrigatório verde e documentação/tracker reconciliados.

### Estado final
- PR permanece OPEN/DRAFT.
- nenhum merge.
- nenhum deploy.
- main não alterada.
- nenhuma conta/provider real.
- nenhuma cobrança real.
- KCA-10 NÃO INICIADO.
