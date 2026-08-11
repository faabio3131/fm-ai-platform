# Gerente IA Operacional V1 — PR20

## Objetivo

Implementar o Gerente IA como orquestrador controlado dos serviços operacionais da
plataforma, sem acesso direto a banco, ORM, SQL, segredos, gateway ou UI. O modelo
não recebe autoridade: ele só pode selecionar tools tipadas em allowlist e preencher
argumentos estritos.

A PR20 segue o plano operacional: **consultas primeiro**, ações por
**preview + confirmação humana**, compras apenas como sugestão e campanhas somente
como rascunho.

## Tools V1

Consultas:

- `consultar_pedidos`
- `consultar_atrasos`
- `consultar_mesas`
- `consultar_cozinha`
- `consultar_entregas`
- `consultar_estoque`
- `sugerir_compra`
- `gerar_relatorio`
- `acompanhar_conversao`

Rascunho:

- `preparar_campanha`

Ações com preview/confirm:

- `priorizar_pedido`
- `pausar_produto`

Não existem tools V1 para publicar campanha, efetuar compra, confirmar pagamento,
fechar caixa, cancelar/concluir pedido ou ajustar estoque diretamente.

## Arquitetura

```text
modelo/cliente
    |
    v
ChamadaTool tipada + allowlist estrita
    |
    v
ServicoGerenteIA
    |-- RBAC + tenant/unidade
    |-- auditoria
    |-- consultas ------------------> services/projeções operacionais
    |-- campanha -------------------> service CRM -> RASCUNHO
    `-- ação -> preview do service -> confirmação humana -> service de domínio
```

`core/gerente_ia/adapters.py` contém apenas Protocols de services/projeções. O
módulo não importa SQLAlchemy, Session, modelos ORM ou secret manager. O antigo
placeholder `core/gerente_ai.py` virou apenas uma facade de compatibilidade.

## Prompt injection

A defesa não depende de detectar frases suspeitas. O desenho é estrutural:

1. o nome da tool precisa pertencer ao enum `ToolGerenteIA`;
2. cada tool possui conjunto fechado de argumentos permitidos e obrigatórios;
3. `tenant_id`, `unidade_id`, papéis, permissões, SQL, token, segredo, confirmação e
   nome de tool não podem vir nos argumentos do modelo;
4. tenant/unidade sempre são derivados de `ContextoExecucao` autenticado;
5. texto retornado por pedidos, CRM ou integrações é marcado como conteúdo não
   confiável e nunca é reinterpretado como chamada de tool;
6. texto de observação que diga “ignore as regras”, por exemplo, permanece apenas
   um campo de resultado;
7. ações mutáveis não são executadas durante a chamada do modelo.

## RBAC e confirmação humana

Consultas exigem `gerente_ia.consultar`. Preparação de campanha e preview exigem
`gerente_ia.preparar_acao`.

Para executar um preview, o confirmador precisa ser identidade humana com papel
`gerente` ou `administrador`, possuir `gerente_ia.executar_acao` e também a
permissão real do domínio:

- priorizar pedido -> `pedido.priorizar`;
- pausar produto -> `configuracao.alterar`.

Identidade técnica/sistema e o próprio papel `gerente_ia` não confirmam ação.

## Preview vinculado ao estado

A preparação consulta o service antes de criar o preview. O preview contém:

- tenant/unidade;
- tool;
- recurso;
- argumentos;
- motivo;
- snapshot de impacto retornado pelo service, incluindo versão quando aplicável;
- usuário que preparou;
- expiração;
- fingerprint SHA-256 de todos esses elementos.

Na confirmação, a fingerprint precisa ser idêntica e o service é consultado outra
vez. Se o snapshot mudou, a execução falha com `preview_desatualizado` e é exigido
novo preview. A reserva de execução é atômica no repositório de preview; retry da
mesma idempotency key retorna o mesmo resultado e outra chave não reutiliza preview
já consumido.

## Campanhas

`preparar_campanha` cria somente `RascunhoCampanha`. O service de campanha é
responsável por calcular audiência elegível a partir do CRM/consentimento. A PR20
não possui operação de publicação. Texto e objetivo podem ser propostos pela IA,
mas consentimento, audiência e envio permanecem autoridades externas ao modelo.

## Compra

`sugerir_compra` é consulta. A V1 não possui tool de compra, aprovação ou pedido a
fornecedor. A sugestão deve ser baseada em projeções do service de estoque/compra e
ser revisada por humano fora do Gerente IA.

## Auditoria

Consultas, previews, rascunhos, execuções e negações de autorização geram
`EventoAuditoria`. Metadados passam pelo sanitizador da fundação de segurança; não
incluem token, segredo, telefone, payload de cartão ou prova bruta de consentimento.

## Voz

A PR20 não implementa adapter de voz. Além disso, origens identificadas como voz de
PDV/caixa são explicitamente recusadas com `voz_no_caixa_nao_suportada_v1`,
conforme a arquitetura V1. Não existe comando automático de voz no caixa.

## Feature flag

`FM_AI_GERENTE_IA_V1=1` somente habilita a V1 quando `FM_AI_TEST_MODE=1`.
Produção permanece fail-closed nesta etapa.

## Rollout / não escopo

Não há nesta PR:

- deploy público;
- migration em banco real;
- conexão com LLM real;
- API key/secret real;
- acesso direto a SQL/ORM;
- publicação real de campanha;
- envio real de WhatsApp/e-mail/SMS;
- compra real;
- ajuste direto de estoque;
- confirmação de pagamento;
- comando de voz no PDV/caixa;
- início da PR21.

A implantação futura deverá injetar adapters sobre os services reais de Pedido,
Central/KDS, Salão, Entrega, Estoque, CRM e relatórios, mantendo os mesmos gates.

## Rollback

Desabilitar `FM_AI_GERENTE_IA_V1`. Como a PR20 é test-only e não cria schema nem
migra dados, o rollback não exige downgrade de banco.
