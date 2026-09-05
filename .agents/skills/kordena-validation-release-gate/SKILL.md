---
name: kordena-validation-release-gate
description: Define como provar mudanças e decidir gates no Coordena. O nome da skill é um identificador técnico legado preservado por compatibilidade. Use ao testar, homologar, revisar regressões, comparar Work e VS Code físico, declarar pronto/aprovado, preparar release ou avaliar falhas conhecidas versus regressões novas.
metadata:
  version: "1.0.2"
  project: "kordena-gerente-ai"
  canonical_product: "coordena"
---

# Coordena Validation & Release Gate

> Compatibilidade: o diretório e o campo `name` ainda usam `kordena-validation-release-gate` como identificador técnico legado. A marca comercial canônica é **Coordena**.

## Objetivo

Separar claramente **implementado**, **tecnicamente validado** e **100% pronto/homologado**. Nunca confunda teste isolado verde com jornada comercial pronta.

## Regra principal

`passou no Work Cloud` = evidência técnica intermediária.

Status final exige, quando aplicável, reprodução no **VS Code/PC físico** no mesmo SHA, runtime/jornada real e demais provas exigidas pelo Documento Mestre.

Resultado de gate técnico `APROVADO` não transforma automaticamente a situação funcional em `CONCLUÍDO`, não equivale à aprovação final da V1 e não autoriza merge por si só.

## Sequência padrão de prova

1. Registre branch e SHA inicial exatos.
2. Confirme working tree e staged/untracked antes de testar.
3. Rode testes direcionados da mudança.
4. Rode fitness tests arquiteturais afetados.
5. Rode regressão proporcional ao raio de impacto.
6. Rode static checks aplicáveis: `py_compile`/compile, Ruff e mypy direcionado.
7. Rode fresh/upgrade/schema convergence quando houver persistência/migration.
8. Compare falhas com baseline conhecido; não classifique automaticamente falha como preexistente sem reprodução/evidência.
9. Reproduza o mesmo candidato fisicamente quando o gate for final/comercial.
10. Execute jornada manual/browser/dispositivo/PostgreSQL/provedor real quando o bloco exigir.
11. Confirme `git status` limpo ou explique todo artefato gerado.
12. Produza parecer de gate e STOP.

## Fitness tests

- Fitness tests não devem ser removidos, mockados ou enfraquecidos apenas para fazer um gate passar.
- Se um fitness test depende de consumidor real, preserve a prova real ou abra nova decisão arquitetural.
- Mudança estrutural nova deve criar fitness test quando o risco não estiver coberto pelos existentes.
- Contagens esperadas são evidência, não objetivo a ser manipulado.

## Falhas e regressões

Classifique cada falha como uma destas categorias:

- `REGRESSÃO INTRODUZIDA` — não existia no baseline comparável.
- `PREEXISTENTE COMPROVADA` — reproduzida no baseline/linha anterior relevante.
- `BLOCKER CONHECIDO DO GATE` — já registrado e explicitamente fora do escopo atual.
- `INFRAESTRUTURA` — tooling, rede, credencial, serviço ou ambiente impede a prova.
- `INCONCLUSIVA` — evidência insuficiente; não declare sucesso.

Não corrija automaticamente falha fora do escopo. Se ela bloqueia a jornada atual, pare no gate e peça decisão.

## Gate técnico versus gate final

### Gate técnico do bloco

Pode ser aprovado quando implementação, fitness tests, regressão dirigida e static checks relevantes estão verdes, com limitações registradas.

Quando a autoridade vigente nomear esse gate como `G3` ou outro identificador, registre também o nome completo e a fonte do gate. Não confunda esse identificador com as Etapas 0–17 do Protocolo Mestre nem com o Gate 0 do Plano V1 ou o Gate de Execução E0.

### Pronto / Aprovado final

Exige as provas práticas relevantes, que podem incluir:

- mesmo SHA no GitHub e VS Code físico;
- navegador real;
- dispositivo real/responsividade quando crítico;
- PostgreSQL descartável/homologação para schema comercial;
- provedor externo real/sandbox oficial quando necessário;
- multi-tenant/unidade prática;
- RBAC deny/allow real;
- persistência/reload/idempotência;
- efeitos econômicos/estoque/pedido/auditoria coerentes;
- nenhuma pendência crítica incompatível com o Documento Mestre.

## Relatório mínimo de gate

Sempre registre:

- `RESULTADO DO GATE`: `APROVADO`, `PARCIAL` ou `BLOQUEADO`;
- `SITUAÇÃO FUNCIONAL`, `ESTADO TÉCNICO/PR` e `ESTADO OPERACIONAL` separadamente, usando os valores oficiais dos protocolos do projeto quando aplicáveis;
- branch/SHA;
- ambiente: Work Cloud, CI, VS Code físico, browser, PostgreSQL etc.;
- testes e contagens;
- static checks;
- jornada executada e até onde chegou;
- falhas classificadas;
- riscos residuais;
- operações Git/produção realizadas ou explicitamente não realizadas;
- próximo STOP.

## Kill switch de repetição

Se a mesma causa raiz continuar falhando após três tentativas corretivas no mesmo gate, **pare de repetir a mesma abordagem**. Classifique o bloqueio, preserve a evidência e entregue hipóteses restantes e decisão necessária. Trabalhos independentes podem continuar somente quando forem seguros, autorizados e não dependerem do gate bloqueado.
