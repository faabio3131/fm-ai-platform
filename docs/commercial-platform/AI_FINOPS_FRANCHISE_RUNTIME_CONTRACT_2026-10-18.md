# Kordena V1 — Contrato operacional de franquias, precificação e Command

**Data:** 18/10/2026. **Fase:** construção, exclusivamente. **Status:** candidata na PR #230.
**Referência de governança:** PR #229; conclusão do código/CI interno antecede provedores reais, pagamentos, homologação e deploy.

## Autoridades existentes e telas

- **FM Command**: interface de configuração comercial em `/dashboard/commercial/kordena`. Integração autenticada existente `KordenaCommercialControlService` → `/v1/control-plane/fmcc/catalog/commands`. Plano, preços, periodicidade e política comercial são dados versionados no catálogo comercial Kordena. **Nenhum preço de venda foi aprovado, predefinido ou publicado** por esta implementação.
- **Kordena Commercial Entitlement**: snapshot local de `plan_version_id`, `revision`, `capabilities_json` e estado da assinatura; nunca perguntar ao Command se deve atender cada requisição.
- **Kordena AI Budget Ledger**: saldo transacional no PostgreSQL (`fm_ai_franchise_budgets_v1`, `fm_ai_franchise_reservations_v1`) é fonte da verdade da proteção de custos, não o dashboard nem o agregado diário.
- **Kordena AI Model Router**: preautoriza cada tentativa antes do provider, concilia uso conhecido com snapshot versionado; timeout/uso indeterminado permanece pendente e reservado.
- **Kordena AI FinOps**: a página existente `/admin/ai-finops` ganhou `GET /v1/ai-finops/franquias`, barra percentual e alertas 70/90/100; não mostra preço interno de modelo, custo do fornecedor ou token de autenticação. A UI não cria direitos nem bloqueia pagamentos.

## Contrato configurável de preços das assinaturas

Os planos comerciais estáveis são `KORDENA_PLAN_A` a `KORDENA_PLAN_D`. O formulário Command prepara rascunhos; publicar preços exige as transições e aprovações da Plataforma Comercial já existente. Informar preço, valor de franquia e margem comercial será decisão posterior do proprietário; **não colocar R$ 89,90, R$ 179,90 ou quaisquer valores exemplificativos em produção**. Periodicidade, moeda e política de migração são atributos configuráveis e sujeitos à validação de alteração contratual.

## Contrato técnico de orçamento interno de IA

O plano pode definir uma capability `ai.budget.<capability_do_router>`. Exemplo de **schema ilustrativo, sem valor financeiro aprovado**:

```json
{
  "capability_key": "ai.budget.tool_planning",
  "enabled": true,
  "limit_value": "<orcamento_de_teste_aprovado>",
  "limit_unit": "USD",
  "config": {
    "scope": "unit",
    "maximo_por_tentativa": "<teto_de_teste_aprovado>"
  }
}
```

**Atenção:** os valores acima são placeholders de documentação, não dados de execução. O ledger só aceita `Decimal` positivo e a mesma revisão da política. O escopo `unit` é obrigatório na versão inicial: uma única franquia por unidade/capability/ciclo, nunca implicitamente compartilhada nem multiplicada entre tenants. O limite em USD é **interno da FM**, não preço do restaurante e não créditos de IA exibidos ao cliente.

A assinatura ativa/reconciliada dispara o provisionamento idempotente de orçamento para unidades autenticadas no Membership Fabric (ciclo derivado de `subscription_id` e início do período). Renovações geram outro ciclo. Alterações de plano/revisão preservam os débitos já incorridos e mudam limites apenas pelo ledger governado; mudanças de custo não permitem gasto retroativo. Plano sem configuração de IA não dá franquia; falta de membership não cria unidade default.

## Rate cards de modelos — diferentes de preços comerciais

Tarifas de OpenAI/Gemini **não** são mensalidades de plano. Devem existir snapshots versionados, de identidade exata do modelo, sob configurações da integração já governada, com vigência, componentes de tarifa e moeda. `price_snapshot` e `price_snapshot_id` são parâmetros da rota. Exemplo estrutural com campos (sem valores reais):

```json
{
  "price_snapshot_id": "<id_de_versao>",
  "provider": "openai",
  "model": "<modelo>",
  "modalidade": "text_tokens",
  "moeda": "USD",
  "versao": 1,
  "vigencia_inicio": "2026-10-18T00:00:00+00:00",
  "vigencia_fim": null,
  "tarifas": [
    {"componente": "input_tokens", "preco": "<preco_aprovado>", "unidades_por_preco": 1000000},
    {"componente": "output_tokens", "preco": "<preco_aprovado>", "unidades_por_preco": 1000000}
  ]
}
```

O código da calculadora reconhece `cached_tokens` quando o componente estiver configurado; modalidades que não possuam uso/preço completo não podem ganhar custo fictício zero. A ativação do controle não configura tarifas nem credenciais sozinha.

## Proteção e ativação

- Variável `FM_AI_FRANCHISE_ENFORCEMENT_ENABLED=1` ou chamada explicitamente com `require_budget_guard=True` impõe Budget Guard no composition root. Sem rate card, entitlement vigente ou orçamento válido: *falha fechada antes do provider*.
- O **default desativado** durante a construção preserva operações existentes e impede que simulações de orçamento se tornem cobranças. Habilitar após documentação, preços internos e políticas comerciais **não é aprovação de release**.
- `request_id`/tentativa/tenant/unidade/ciclo geram identificador idempotente; replay não executa provider de novo. Reservas pendentes não são desbloqueadas sem evidência de custo ou ausência comprovada de cobrança.
- Não liberar crédito por exibição no painel nem consultar Command no caminho crítico. Separação entre reservas técnicas e franquia comercial do cliente é obrigatória; não exibir custo interno em dólares como um pacote de créditos.

## Matriz de encerramento

**Construção interna:** cálculo monetário, injeção de catálogo, ledger/migration, guard, entitlement, provisionamento de ciclo, UI existente, APIs e testes unitários/contrato/regressão e PostgreSQL descartável verdes. A fonte `AI FinOps Projector` já existe; agendamento/cutover ainda deve ser rastreado separadamente. Rotas que contornem o gateway devem ser eliminadas antes de chamar construção de 100%.

**Posterior à construção:** escolher valores comerciais, cadastrar preços e franquias aprovados, credenciais e faturamento real, homologar rate cards/consumo externo, testes de campo com restaurantes e autorização separada de publicação em produção.

**A integridade econômica vem antes do rótulo 100%:** ausência de preço, budget ou origem de uso válida nunca vira `R$ 0` ou execução ilimitada.
