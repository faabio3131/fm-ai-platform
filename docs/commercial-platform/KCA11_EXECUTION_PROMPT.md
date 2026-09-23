# PROMPT MESTRE — KCA-11

## Expiração + Paywall + Recovery

### Missão
Fechar a jornada comercial do trial após o KCA-G10, garantindo expiração autoritativa, bloqueio comercial fail-closed sem perda de dados e recuperação automática quando a assinatura volta a um estado comercial permitido.

### Dependências
- KCA-07 / KCA-G7: PASS.
- KCA-08 / KCA-G8: PASS.
- KCA-09 / KCA-G9: PASS.
- KCA-09B / KCA-G9B: PASS.
- KCA-10 / KCA-G10: PASS.
- staging integrada em `9867651dc5422ff21f91392bdae9ce44afa536f3`.

### Escopo canônico
Implementar:
1. expiração determinística de trial baseada em servidor/UTC;
2. processamento seguro de trials vencidos mesmo se scheduler atrasar;
3. recálculo de entitlement para `TRIAL_EXPIRED` / `BILLING_ONLY`;
4. gate comercial de request no Kordena;
5. paywall para usuário autenticado sem acesso comercial operacional;
6. superfície mínima permitida: conta, planos, checkout/assinatura, suporte e logout;
7. preservação integral dos dados operacionais após expiração;
8. recovery após assinatura ativa/pagamento reconciliado;
9. atualização da projeção local de entitlement;
10. restauração do acesso sem intervenção manual no banco;
11. auditoria, correlação e evidência;
12. testes de regressão e segurança do KCA-G11.

### Regras críticas
- browser não decide expiração;
- ausência/estado inválido de entitlement nunca libera acesso;
- scheduler atrasado não pode prolongar trial além de `ends_at`;
- paywall não apaga nem modifica dados operacionais;
- usuário expirado continua podendo autenticar;
- módulos comerciais protegidos permanecem bloqueados;
- APIs protegidas também bloqueiam, independentemente da UI;
- billing/checkout usa serviços canônicos existentes; frontend não grava estado comercial;
- assinatura ACTIVE deve recalcular entitlement pela autoridade canônica;
- recovery é idempotente;
- nenhum acesso cross-tenant;
- nenhum bypass por header/rota/client-side;
- nenhuma cobrança/provider/credencial real;
- KCA-12/FM Control Center fora do escopo.

### Fluxo esperado
```text
TRIAL_ACTIVE
→ now_utc >= ends_at
→ TRIAL_EXPIRED
→ entitlement recalculado
→ access_mode = BILLING_ONLY
→ projeção local Kordena
→ request gate bloqueia módulos operacionais
→ UI apresenta paywall

assinatura/pagamento canônico confirmado
→ SUBSCRIPTION_ACTIVE
→ entitlement recalculado
→ projeção local atualizada
→ acesso restaurado
```

### Paywall
Permitido:
- autenticar;
- visualizar conta comercial mínima;
- listar planos;
- iniciar/continuar checkout;
- consultar estado de assinatura/cobrança permitido;
- acessar suporte;
- logout.

Negado:
- PDV;
- Salão;
- KDS;
- operações administrativas do estabelecimento;
- demais módulos operacionais protegidos conforme contrato atual.

### Scheduler / Expiração
Deve existir execução determinística reprocessável para localizar trials ACTIVE vencidos.
Requisitos:
- UTC;
- idempotência;
- lote/limite explícito;
- concorrência segura;
- nenhuma regressão de estado;
- evento/auditoria;
- entitlement sincronizado.

Além do scheduler, o request gate deve validar temporalmente o entitlement/trial aplicável para não depender exclusivamente da pontualidade do job.

### Recovery
O caminho de recuperação deve reutilizar:
- Subscription Engine KCA-08;
- Billing Provider boundary KCA-09;
- Webhook Inbox/Reconciliation KCA-10;
- Entitlement Authority KCA-04;
- projeção local Kordena.

Nenhuma autoridade paralela deve ser criada.

### Testes obrigatórios
- expiração no boundary exato;
- trial ainda válido;
- scheduler atrasado;
- execução repetida/idempotente;
- login após expiração;
- tentativa de operar módulo protegido;
- tentativa direta à API protegida;
- paywall permite planos/checkout/suporte/logout;
- dados operacionais preservados;
- assinatura ACTIVE restaura entitlement;
- recovery repetido não duplica efeitos;
- stale/missing entitlement fail-closed;
- tenant A não recupera/bloqueia tenant B;
- regressão completa dos KCA anteriores.

### Gate KCA-G11
PASS somente com:
- targeted KCA tests verdes;
- regressão Python completa verde;
- testes Web/Node verdes;
- ESLint/TypeScript/Next build verdes;
- migration/schema checks verdes se houver mudança de schema;
- security/tenant isolation verdes;
- CI obrigatório 100% verde;
- implementation record e tracker reconciliados;
- nenhuma falha crítica/alta aberta relacionada ao escopo.

### Governança
- PR permanece OPEN/DRAFT durante execução;
- nenhum merge até KCA-G11 PASS e recertificação do HEAD documental;
- nenhum deploy público;
- `main` não alterada;
- nenhum cliente/provider/credencial/cobrança real;
- KCA-12 NÃO INICIADO.
