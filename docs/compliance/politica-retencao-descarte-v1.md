# Política de Retenção e Descarte de Dados — V1

**Status:** VIGENTE PARA HOMOLOGAÇÃO PRÉ-COMERCIAL

**Produção / uso comercial:** NÃO AUTORIZADOS POR ESTA VERSÃO

**Projeto:** F&M Tecnologia / FM AI Platform

**Versão:** `v1-pre-comercial`

## 1. Objetivo

Definir os critérios de retenção, eliminação, anonimização e descarte seguro aplicáveis à fase atual de desenvolvimento e homologação, mantendo uma separação explícita entre testes pré-comerciais e a futura operação de produção.

Esta política é um instrumento interno de governança. Ela não substitui parecer jurídico, obrigações legais, fiscais, consumeristas, contratuais ou regulatórias que venham a incidir na operação comercial.

## 2. Estado atual do projeto

O titular declarou em 12/08/2026 que atua atualmente como pessoa física e constituirá CNPJ antes do uso comercial dos produtos.

Nesta fase:

- não há autorização para uso comercial;
- a homologação deve utilizar dados sintéticos ou anonimizados;
- credenciais reais de clientes, gateways ou marketplaces não devem ser usadas;
- dados de produção não devem ser copiados para o ambiente de teste;
- o Gate E de produção permanece bloqueado por desenho até o gate pré-lançamento.

## 3. Regras gerais

1. Dados pessoais, quando houver tratamento aplicável, devem observar finalidade, necessidade, segurança e base jurídica adequada.
2. Dados de homologação devem ser sintéticos ou anonimizados sempre que possível.
3. Segredos, tokens, credenciais e chaves não devem ser gravados no repositório nem em artefatos de evidência.
4. Backups de teste devem ser temporários, criptografados quando persistidos e eliminados após a validação técnica.
5. Evidências técnicas devem evitar PII e conter apenas o necessário para auditoria.
6. Nenhum dado de produção pode ser usado para contornar a ausência de uma política comercial definitiva.
7. O lançamento comercial exige nova versão desta política, aprovada após a constituição do controlador comercial e a análise dos tratamentos reais.

## 4. Matriz de retenção — fase pré-comercial

| Categoria | Ambiente | Conteúdo permitido | Retenção V1 | Destino final | Estado |
|---|---|---|---|---|---|
| Banco SQLite de homologação | Homologação | Dados sintéticos/anonimizados | Efêmero durante a execução | Exclusão ao término do runner | Vigente |
| Backup de homologação | Homologação | Cópia de teste criptografada | Somente durante backup/restore | Exclusão após validação | Vigente |
| Artefatos Gate E | Homologação | JSON sem banco bruto/PII | 14 dias conforme workflow | Expiração automática | Vigente |
| Logs de homologação | Homologação | Sem segredos/PII intencional | Conforme política do provedor | Expiração conforme configuração | Vigente |
| Credenciais e segredos | Todos | Nunca em texto no repositório | Enquanto necessários ao serviço | Rotação/revogação e exclusão segura | Regra obrigatória |
| Dados cadastrais de clientes | Produção | **Não autorizados nesta fase** | Definir no gate pré-lançamento | Definir no gate pré-lançamento | Bloqueado |
| Pedidos/comandas reais | Produção | **Não autorizados nesta fase** | Definir no gate pré-lançamento | Definir no gate pré-lançamento | Bloqueado |
| Dados financeiros/fiscais reais | Produção | **Não autorizados nesta fase** | Definir conforme obrigações aplicáveis | Definir no gate pré-lançamento | Bloqueado |
| CRM/marketing real | Produção | **Não autorizado nesta fase** | Definir por finalidade/base legal | Definir no gate pré-lançamento | Bloqueado |
| Auditoria de usuários reais | Produção | **Não autorizada nesta fase** | Definir por risco/necessidade | Definir no gate pré-lançamento | Bloqueado |

Os itens de produção não são “pendências” da homologação: são capacidades deliberadamente bloqueadas até a formalização da operação comercial.

## 5. Procedimento de descarte em homologação

Para os dados de teste e suas cópias:

- eliminar arquivos temporários ao término do runner;
- eliminar cópias de backup após a validação de restore;
- não publicar banco bruto como artefato;
- não registrar segredos ou PII intencional em logs;
- manter apenas evidências técnicas mínimas e temporárias;
- revogar ou rotacionar qualquer credencial de teste que deixe de ser necessária.

## 6. Pessoa natural e agente de pequeno porte

A Resolução CD/ANPD nº 2/2022 inclui pessoas naturais no conceito de agentes de tratamento de pequeno porte quando realizam tratamento assumindo obrigações típicas de controlador ou operador. O regulamento também prevê dispensa de indicação de encarregado para agentes de pequeno porte elegíveis, com manutenção de canal de comunicação com titulares quando aplicável.

A elegibilidade ao regime diferenciado e a avaliação de alto risco deverão ser refeitas no lançamento comercial, pois dependem da operação concreta, escala, riscos e demais critérios regulatórios.

Referência oficial:

- Resolução CD/ANPD nº 2/2022 — https://www.gov.br/anpd/pt-br/acesso-a-informacao/institucional/atos-normativos/regulamentacoes_anpd/resolucao-cd-anpd-no-2-de-27-de-janeiro-de-2022

## 7. Direitos de titulares

A fase atual não autoriza ingestão de dados reais de clientes para homologação. Se, excepcionalmente, qualquer dado pessoal real for introduzido, o teste deve ser interrompido e o caso deve ser tratado segundo a LGPD e a governança aplicável antes de prosseguir.

Para produção, os mecanismos de atendimento aos direitos dos titulares deverão estar definidos e validados no gate pré-lançamento comercial.

## 8. Gate obrigatório antes do lançamento comercial

Nenhum lançamento comercial pode ocorrer sem o cumprimento integral de `docs/compliance/gate-pre-lancamento-comercial-v1.md`.

Esse gate exige, entre outros pontos:

- CNPJ/controlador constituído e identificado;
- responsabilidades de controlador e operadores definidas;
- inventário real de tratamentos;
- bases legais/finalidades registradas;
- prazos de retenção de produção definidos;
- canal de titulares;
- avaliação de alto risco;
- decisão documentada sobre encarregado/DPO;
- contratos, segurança, incidentes e privacidade revalidados;
- novo GO técnico e decisão humana separada de produção.

## 9. Relação com o Gate E

O Gate E técnico de produção pode permanecer com `legal_approval=false` enquanto o projeto estiver pré-comercial. Esse valor funciona como trava de produção e não invalida a conclusão da homologação interna com dados de teste.

Estados válidos:

- `HOMOLOGACAO_PRE_COMERCIAL_CONCLUIDA`
- `PRODUCAO_BLOQUEADA_ATE_GATE_PRE_LANCAMENTO`

## 10. Controle de versão

- Versão: `v1-pre-comercial`
- Data de vigência interna: `2026-08-12`
- Escopo: desenvolvimento e homologação pré-comercial
- Estado da produção: bloqueada
- Próxima revisão obrigatória: antes da constituição do ambiente comercial/produção e após a definição do CNPJ/controlador
