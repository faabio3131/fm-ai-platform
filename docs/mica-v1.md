# Mica V1 — conversa, carrinho, pedido e pagamento seguros

> **Compatibilidade transitória:** este documento descreve o módulo histórico `core/mica`, mantido temporariamente durante o cutover controlado. A identidade oficial da funcionalidade é **Assistente de Atendimento**, com nome público configurável por tenant/unidade. O módulo legado não deve ser apresentado como nome de produto ou identidade pública.

## Objetivo

A PR15 substitui o fluxo legado da Mica por uma orquestração explícita e segura entre **Conversa → Carrinho → confirmação do cliente → Pedido → Pagamento → resposta/pós-venda ou handoff humano**.

A IA fica limitada à interpretação estruturada da conversa. Ela não grava `Venda`, não baixa estoque, não escolhe um produto substituto, não confirma pagamento e não altera diretamente os agregados operacionais.

## Problemas removidos do fluxo legado

O fluxo anterior misturava interpretação da IA, busca de produto, criação de `Venda`, baixa de estoque e inferência de pagamento dentro da UI. Em caso de erro da IA, havia fallback com produto fixo; quando um item não era encontrado, o código podia selecionar o primeiro produto do banco; e a venda era criada com pagamento `Aprovado` sem confirmação financeira autoritativa.

A PR15 remove esse bloco executável da aba da Mica e o substitui por `core.mica`.

## Fluxo normativo

1. A conversa recebe uma mensagem e um identificador de mensagem.
2. A IA deve responder JSON puro no schema estrito da Mica.
3. O serviço resolve cada item **somente por nome exato normalizado** no catálogo do mesmo tenant/unidade.
4. Qualquer schema inválido, item ausente ou ambíguo gera `handoff_humano`; não existe fallback para produto fixo ou primeiro item.
5. Um `CarrinhoMica` é congelado com fingerprint e total em `Decimal`.
6. Nenhum efeito operacional ocorre antes da confirmação explícita do cliente.
7. Para confirmar, o fingerprint atual deve ser exatamente o que o cliente revisou; alteração exige nova confirmação.
8. O Pedido é criado por uma porta de serviço com chave de idempotência própria.
9. O Pagamento é criado por uma porta financeira independente, também idempotente.
10. A Mica apenas exibe o status devolvido pela fonte financeira: `pendente` continua pendente; pagamento na entrega continua `aguardando_entrega`; `pago` só é mostrado se o domínio financeiro devolver `PAGO`.
11. Falhas que exigem decisão humana geram handoff, sem inventar conclusão.

## Schema estrito

A resposta da IA aceita exatamente:

```json
{
  "cliente_nome": "Cliente WhatsApp",
  "itens": [
    {"nome_produto": "Nome exato do cardápio", "quantidade": 1}
  ],
  "resposta_whatsapp": "Resumo para conferência"
}
```

Não são aceitos markdown, chaves extras, carrinho vazio, quantidade booleana/não inteira, quantidade menor que 1 ou maior que 100. O parser não corrige respostas inválidas.

## Invariantes

- zero fallback inventado;
- zero seleção do primeiro produto;
- zero correspondência parcial silenciosa;
- zero `Venda` criada diretamente pela Mica;
- zero baixa direta de estoque pela Mica;
- zero pagamento marcado como aprovado a partir de texto da IA;
- Pedido e Pagamento são efeitos separados;
- confirmação explícita do carrinho é obrigatória;
- fingerprint protege contra confirmação de carrinho alterado;
- Pedido e Pagamento usam chaves de idempotência distintas;
- catálogo e efeitos são isolados por tenant/unidade;
- telefone usado pela UI V1 vira referência opaca por SHA-256 antes de entrar no núcleo da Mica;
- falha de IA ou resolução de catálogo termina em handoff seguro.

## Portas operacionais

`PortaPedidosMica`, `PortaPagamentosMica` e `PortaHandoffMica` desacoplam a Mica dos bancos e UIs legados. Nesta PR, o caminho executável permanece somente em runtime de teste e usa `OperacaoMicaFake`, que é determinístico e não toca `Venda`, estoque ou gateway real.

A ligação de produção com repositories/services autoritativos deve ocorrer em etapa de rollout/homologação, sem reintroduzir acesso direto ao banco pela IA.

## Feature flag e rollout

`FM_AI_MICA_V1=1` só habilita a Mica V1 quando `FM_AI_TEST_MODE=1`. Fora do runtime de teste, a funcionalidade fica fail-closed nesta etapa.

Isso permite validar o novo contrato e remover o fluxo legado perigoso sem executar pedidos, pagamentos ou mensagens reais.

## Rollback

- desabilitar `FM_AI_MICA_V1` desativa a execução V1;
- não há migration de banco nesta PR;
- não há dado de produção criado pela Mica V1 nesta etapa;
- o rollback do código não exige compensação financeira ou de estoque porque o runtime habilitado é isolado de teste.

## Não escopo

- delivery próprio completo (PR16);
- gateway/adquirente real;
- WhatsApp real;
- migration em banco real;
- deploy de produção;
- campanhas/CRM da PR19;
- Gerente IA da PR20.

## Critérios de aceite da PR15

- schema estrito validado;
- resolução exata de catálogo;
- erro/ambiguidade gera handoff;
- confirmação explícita e reconfirmação por fingerprint;
- Pedido e Pagamento idempotentes por portas independentes;
- Pix pendente nunca promovido a pago pela Mica;
- pagamento na entrega permanece `aguardando_entrega`;
- isolamento multiempresa/unidade;
- fluxo legado de fallback/primeiro produto/Venda aprovada/baixa direta removido da aba executável;
- testes unitários, integração, E2E da Mica e regressões anteriores verdes.
