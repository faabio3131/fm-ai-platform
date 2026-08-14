# Plano de Pull Requests — evolução operacional V2

Este plano começa somente depois da conclusão técnica da V1 e do hardening do Gate E. A V2 transforma os contratos e runtimes hoje seguros/testáveis em uma plataforma progressivamente utilizável em homologação, sem antecipar produção ou comercialização.

> **Correção de escopo do Gate Final Interno V1:** a composição de consultas reais,
> os adapters internos necessários, a correlação operacional e o entrypoint do
> Gerente IA eram descritos abaixo como PR22–24. Esses itens são necessários para
> o Core cumprir seu requisito obrigatório de gerente geral e foram
> [reclassificados como gates da V1](gate-final-interno-core-runtime-v1.md). A
> numeração histórica abaixo não autoriza tratá-los como expansão da V2 nem
> encerrar a V1 sem implementá-los e validá-los.

## Princípios da V2

1. Nenhum modelo de IA recebe autoridade direta sobre banco, pagamentos, estoque, campanhas, pedidos ou integrações externas.
2. Tenant, unidade, usuário e permissões continuam derivados do contexto autenticado; nunca dos argumentos do modelo.
3. Toda ação mutável continua usando service de domínio, idempotência, auditoria e, quando crítica, preview + confirmação humana.
4. Credenciais reais nunca entram no repositório; integrações externas reais começam em sandbox/homologação e atrás de flags específicas.
5. Voz é uma interface de entrada, não uma autoridade. Transcrição é conteúdo não confiável e passa pelos mesmos contratos do Gerente IA.
6. PDV/caixa continua sem comando de voz automático. A V2 pode oferecer voz assistiva ao Gerente IA fora do fluxo automático de caixa.
7. Migração real, deploy público, ativação de credenciais de produção e uso comercial continuam bloqueados pelo Gate Pré-Lançamento Comercial e por aprovação humana separada.
8. Cada PR deve manter rollback claro e nenhum PR seguinte começa automaticamente após merge.

## Ordem proposta

| PR planejada | Escopo e entregável | Dependência / aceite principal |
|---:|---|---|
| 22 | **Composition root e adapters internos de consulta do Gerente IA:** ligar `PortaConsultasGerenciais` às projeções/services reais já existentes, somente leitura, em runtime local/homologação; nenhum SQL/ORM direto no Gerente IA | V1/PR20–21; tenant/RBAC, sem PII excessiva, testes de contrato e integração; produção fail-closed |
| 23 | **Adapters internos de ação do Gerente IA:** conectar priorização de pedido e pausa de produto aos services de domínio reais, preservando preview, confirmação humana, estado/fingerprint, idempotência e auditoria | PR22; concorrência, stale preview, replay e segregação de função testados |
| 24 | **Gateway de LLM provider-neutral em homologação:** adapter externo atrás de interface estável, budgets/timeouts/retry/circuit breaker, logs minimizados e nenhum segredo no prompt/log; um provedor pode ser habilitado por vez em homologação | PR22–23; prompt injection continua contido por tools tipadas; sem credencial de produção |
| 25 | **Voz assistiva do Gerente IA:** entrada por áudio/transcrição para consultas e preparação de ações; confirmação crítica continua explícita e visual/humana; voz de PDV/caixa automático permanece proibida | PR24; acessibilidade, consentimento de microfone, minimização/retensão de áudio e testes de ambiguidade |
| 26 | **Integrações externas reais em sandbox/homologação:** iFood primeiro quando contrato oficial e credenciais de sandbox estiverem disponíveis; 99Food/Keeta somente com documentação oficial verificável; gateway de pagamento e WhatsApp em adapters separados | PR17–18 + Gate E; assinatura/webhook, idempotência, reconciliação, DLQ e secrets manager; nenhum tráfego de produção |
| 27 | **Control plane SaaS pré-comercial:** onboarding de empresa/unidade, papéis, feature flags, configuração isolada por tenant, limites de plano e trilha administrativa; sem cobrança real | PR2 + V1 multiempresa; testes IDOR e isolamento; dados comerciais ainda fictícios/homologação |
| 28 | **Medição de uso e billing sandbox:** eventos de consumo, quotas, plano/assinatura, fatura simulada e reconciliação interna; nenhuma cobrança/adquirente de produção | PR27; valores em Decimal, idempotência e trilha financeira; fiscal/tributário real fora do escopo até definição empresarial |
| 29 | **Privacidade/operabilidade comercial:** fluxo de direitos dos titulares, inventário técnico de tratamentos, exportação/anonimização controlada, observabilidade, suporte e resposta a incidentes sem exposição cross-tenant | PR27–28; Gate Pré-Lançamento continua NO-GO enquanto itens legais/empresariais estiverem incompletos |
| 30 | **Gate F pré-comercial:** novo release candidate, reexecução do Gate E em homologação representativa, restore/rollback, carga/caos, segurança, privacidade, acessibilidade, SLOs, integrações sandbox e checklist do Gate Pré-Lançamento | Todos; produz somente recomendação GO/NO-GO. Deploy/migration/ativação comercial exigem aprovações humanas separadas |

## PR22 — referência histórica reclassificada como Gate Core V1

A PR22 deve ser pequena e exclusivamente de leitura. O objetivo é tornar o Gerente IA capaz de consultar dados operacionais por adapters reais de aplicação, sem ampliar sua autoridade.

### Entregáveis mínimos

- `composition root` ou fábrica explícita para montar `ServicoGerenteIA` sem importar UI/Streamlit dentro do domínio;
- adapters para consultas de pedidos, atrasos, mesas, cozinha, entregas, estoque, sugestão de compra, relatório e conversão, usando apenas services/projeções existentes;
- contrato de minimização: retorno gerencial agregado e somente campos necessários;
- tenant/unidade sempre recebidos do contexto autenticado e propagados aos services;
- feature flag própria de homologação, fail-closed por padrão;
- testes negativos de cross-tenant/IDOR e tentativa de sobrescrever tenant/unidade pelos argumentos da IA;
- testes de integração com banco/fixtures isolados, nunca banco real;
- nenhuma action mutável conectada nesta PR.

### Não escopo da PR22

- LLM externo real;
- voz;
- pagamento/gateway;
- marketplace real;
- WhatsApp real;
- migration de produção;
- deploy público;
- campanha publicada;
- compra automática;
- mudança de estoque;
- mudança de pedido;
- cobrança SaaS.

## Gates da V2

- **Gate V2-A (PR23):** Gerente IA lê e prepara/executa somente as ações já autorizadas através de services reais em homologação, com RBAC/auditoria/preview intactos.
- **Gate V2-B (PR25):** LLM e voz entram como interfaces não confiáveis sem aumentar autoridade; ações críticas seguem confirmação humana.
- **Gate V2-C (PR26):** integrações externas passam sandbox/homologação com idempotência, reconciliação e secrets corretos.
- **Gate V2-D (PR28):** control plane, tenant e billing sandbox funcionam sem vazamento cross-tenant e sem cobrança real.
- **Gate F (PR30):** valida preparação pré-comercial; não substitui CNPJ, governança legal, aprovação de produção, deploy ou migration.

## Itens explicitamente adiados

Fiscal/contábil completo, roteirização logística avançada, automação de compra a fornecedor, publicação autônoma de campanhas e qualquer comando de voz automático no PDV/caixa ficam fora desta sequência inicial. Se forem priorizados depois, devem nascer em PRs próprios, com novos contratos, threat model e aprovação humana.

## Regra de avanço

A conclusão de uma PR não autoriza a próxima automaticamente. Cada nova PR, merge, deploy, migration, ativação de credencial externa ou mudança de produção exige autorização humana explícita. Enquanto o Gate Pré-Lançamento Comercial estiver incompleto, o estado permanece `NO_GO_COMERCIAL`.
