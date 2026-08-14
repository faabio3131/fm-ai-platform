# Gate Final Interno V1 — Core e Runtime

> Registro histórico da auditoria anterior à execução. O resultado implementado
> está em `gate-final-interno-core-runtime-v1-executado.md`.

## Decisão

A composição do Gerente IA com dados e services reais é uma pendência obrigatória
da V1. A antiga classificação dessa composição como PR22/V2 conflita com o
requisito canônico de que o Core seja o gerente geral efetivamente funcional e,
por isso, não pode ser usada para encerrar a V1.

Esta decisão não autoriza merge, deploy, migration real, credenciais externas,
tráfego de produção nem transformação visual.

## Estado comprovado em 14/08/2026

- `ServicoGerenteIA` não é instanciado por nenhum entrypoint de produção;
- o único runtime completo é `RuntimeGerenteIATeste`, composto por fakes;
- `ConsultasGerenciaisSQLAlchemy` existe, mas é chamado diretamente apenas em
  testes e não está conectado ao serviço, autenticação, UI ou API;
- não existe consumer do Event Bus para o Core receber e correlacionar eventos;
- não existem adapters persistentes de ações, campanhas ou previews do Gerente IA;
- `acompanhar_conversao` falha com
  `persistencia_crm_comercial_ainda_indisponivel`;
- o adapter atual lê pedidos, produção/KDS, mesas, entregas, estoque, receita
  confirmada e prontidão de integrações, mas não entrega ainda a visão financeira
  omnicanal, CRM, marketplaces, rotas/ETA, Mica, PDV detalhado ou proveniência
  suficiente para conclusões gerenciais;
- as chamadas legadas ao Gemini em `app.py` não passam por `ServicoGerenteIA` nem
  pelo controle de configuração tenant/unidade.

Consequentemente, o Core possui contratos de segurança e orquestração validados,
mas sua situação funcional no runtime é **PARCIAL**.

## Plano seguro de conclusão dentro da V1

### Gate Core V1-A — fontes reais e consultas

1. criar um composition root explícito fora do domínio e do Streamlit;
2. montar o Core com identidade autenticada, RBAC, tenant/unidade e auditoria
   SQLAlchemy;
3. completar as projeções reais para pedidos, pagamentos/financeiro, estoque,
   KDS, salão, PDV, entrega/expedição, CRM e integrações;
4. implementar filtros declarados, limites, minimização de PII e proveniência
   (`fonte`, versão, timestamp e correlation ID);
5. manter produção fail-closed enquanto os gates não estiverem aprovados.

Aceite: uma consulta atravessa entrypoint autenticado, `ServicoGerenteIA`,
projeções reais e banco descartável, com prova negativa cross-tenant e auditoria.

### Gate Core V1-B — correlação e inteligência operacional

1. registrar consumer idempotente e allowlisted do Event Bus para o Core;
2. produzir visão operacional unificada sem duplicar as fontes autoritativas;
3. correlacionar pedido, pagamento, produção, estoque, entrega, canal e cliente;
4. detectar exceções e riscos por regras determinísticas rastreáveis;
5. gerar recomendações com justificativa, impacto esperado e fontes utilizadas.

Aceite: cenários ponta a ponta comprovam detecção e correlação, replay seguro,
ordem fora de sequência, origem dos dados e isolamento tenant/unidade.

### Gate Core V1-C — ações e campanhas seguras

1. criar repositório persistente de preview/idempotência;
2. conectar priorização de pedido aos services canônicos de Pedido/KDS;
3. criar uma autoridade canônica de disponibilidade antes de permitir pausa de
   produto, sem escrever diretamente nas tabelas legadas sem tenant;
4. implementar persistência CRM e adapter de campanha somente em rascunho;
5. preservar preview, fingerprint, confirmação humana, RBAC e auditoria.

Aceite: ação real em banco descartável exige confirmação humana, rejeita stale
preview/replay conflitante e não permite que o modelo amplie a própria autoridade.

### Gate Core V1-D — entrada operacional e validação

1. expor o Core em entrypoint autenticado do produto;
2. manter chamadas tipadas disponíveis mesmo sem provedor LLM;
3. ligar linguagem natural ao gateway tenant-scoped somente quando houver
   credencial homologada, sem transferir autoridade ao modelo;
4. executar unitários, integração, API, segurança, regressão, E2E e CI;
5. validar manualmente o fluxo no navegador antes da estabilização funcional.

Aceite: fluxo `usuário autenticado -> Core -> dados reais -> explicação/origem ->
preview -> confirmação humana -> efeito -> auditoria` aprovado. Ativação do LLM
real permanece bloqueada por credencial externa, mas o runtime interno deve estar
completo e testável sem ela.

## Separação de dependências

São internas e pertencem à V1: composition root, projeções, persistência CRM e
previews, consumer de eventos, correlação, regras de exceção/recomendação,
adapters de ações/campanhas, entrypoint, RBAC, auditoria e testes.

Dependem de ambiente externo: contas e credenciais de provedores, sandbox real,
webhooks públicos, quotas/billing, migração em banco real, deploy e homologação de
tráfego externo.

## Regra de avanço

A execução dos Gates Core V1-A a V1-D altera arquitetura central e requer
autorização explícita do responsável pelo produto. A transformação visual premium
continua bloqueada até a estabilização funcional da V1.
