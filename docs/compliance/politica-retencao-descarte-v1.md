# Política de Retenção e Descarte de Dados — V1

**Status:** MINUTA — NÃO APROVADA JURIDICAMENTE

**Projeto:** F&M Tecnologia / FM AI Platform

**Escopo:** homologação V1 e preparação para produção.

## 1. Objetivo

Definir critérios mínimos de retenção, eliminação, anonimização e descarte seguro de dados tratados pela plataforma, respeitando finalidade, necessidade, segurança, prevenção e prestação de contas.

Esta minuta não substitui parecer jurídico, análise do encarregado/DPO ou obrigações legais, fiscais, trabalhistas, consumeristas, contratuais ou regulatórias aplicáveis ao negócio.

## 2. Regras gerais

1. Dados pessoais só devem ser mantidos enquanto houver finalidade válida e base jurídica aplicável.
2. Encerrada a finalidade do tratamento, os dados devem ser eliminados ou anonimizados, salvo hipótese legal de conservação.
3. A retenção deve ser mínima, justificada e documentada por categoria de dado.
4. Dados de teste e homologação devem ser sintéticos ou anonimizados sempre que possível.
5. Segredos, tokens, credenciais e chaves não devem ser gravados no repositório nem em artefatos de evidência.
6. Backups de teste devem ser temporários, criptografados quando persistidos e eliminados após a validação técnica.
7. Evidências técnicas devem evitar PII e conter apenas o necessário para auditoria.
8. Toda exceção de retenção deve registrar responsável, fundamento, prazo e destino final.

## 3. Matriz de retenção V1

| Categoria | Ambiente | Conteúdo permitido | Retenção V1 | Destino final | Status |
|---|---|---|---|---|---|
| Banco SQLite de homologação | Homologação | Dados sintéticos/anonimizados | Efêmero durante a execução | Exclusão ao término do runner | Técnico definido |
| Backup de homologação | Homologação | Cópia de teste criptografada | Somente durante backup/restore | Exclusão após validação | Técnico definido |
| Artefatos Gate E | Homologação | JSON sem banco bruto/PII | 14 dias conforme workflow atual | Expiração automática do artefato | Técnico definido |
| Logs de homologação | Homologação | Sem segredos/PII intencional | Conforme política operacional do provedor | Expiração conforme configuração aplicável | Revisar antes de produção |
| Dados cadastrais de clientes | Produção | Mínimo necessário | A definir pelo Jurídico/DPO | Eliminação ou anonimização | Pendente aprovação |
| Dados de pedidos/comandas | Produção | Dados necessários à operação | A definir conforme obrigações aplicáveis | Eliminação/anonimização quando cabível | Pendente aprovação |
| Dados financeiros/fiscais | Produção | Dados exigidos para a finalidade | A definir conforme obrigações legais/regulatórias | Descarte após prazo aplicável | Pendente aprovação |
| Dados de CRM/marketing | Produção | Somente com fundamento e consentimento quando aplicável | A definir por finalidade | Eliminação após término da finalidade ou solicitação válida | Pendente aprovação |
| Auditoria e segurança | Produção | Identificadores e metadados mínimos | A definir por risco e necessidade | Eliminação segura | Pendente aprovação |
| Credenciais e segredos | Todos | Nunca em texto no repositório | Enquanto necessários ao serviço | Rotação/revogação e exclusão segura | Regra obrigatória |

## 4. Procedimento de descarte

Para cada categoria aprovada, o descarte deverá observar:

- confirmação de que a finalidade terminou ou que o prazo aprovado expirou;
- verificação de eventual obrigação de conservação;
- eliminação segura ou anonimização quando juridicamente adequada;
- propagação do descarte às cópias sob controle da empresa, respeitando limitações técnicas e legais;
- registro mínimo de auditoria sem preservar o conteúdo eliminado;
- revogação/rotação de credenciais quando o descarte envolver segredos.

## 5. Solicitações de titulares

Pedidos de acesso, correção, eliminação, revogação de consentimento ou demais direitos devem ser avaliados conforme a LGPD e as hipóteses legais de conservação. A plataforma não deve eliminar automaticamente dados sujeitos a obrigação legal ou regulatória sem validação adequada.

## 6. Homologação Gate E

Para o Gate E atual:

- o release candidate permanece imutável;
- o banco é isolado e de teste;
- nenhum dado de produção deve ser usado;
- artefatos não devem conter banco bruto ou PII;
- a evidência de privacidade só poderá ser marcada como aprovada após aceite humano jurídico/DPO desta política ou de versão substituta formalmente aprovada.

## 7. Aprovação necessária

Antes de qualquer GO técnico para produção, o Jurídico/DPO deve revisar e decidir, no mínimo:

- categorias de dados efetivamente tratadas;
- finalidade e fundamento de cada tratamento;
- prazos de retenção de produção;
- hipóteses de conservação após término do tratamento;
- procedimento de eliminação/anonimização;
- tratamento de backups e logs;
- atendimento de direitos dos titulares;
- responsabilidades entre controlador, operador, fornecedores e suboperadores.

A aprovação deve ser registrada em documento/issue auditável contendo nome ou identificação do responsável, função, data, versão da política e decisão explícita.

## 8. Referências oficiais para revisão

- Lei nº 13.709/2018 — LGPD, especialmente princípios do art. 6º e regras de término/conservação dos arts. 15 e 16.
- Orientações e perguntas frequentes da Autoridade Nacional de Proteção de Dados — ANPD.
- Guia Orientativo sobre Segurança da Informação para Agentes de Tratamento de Pequeno Porte — ANPD.

## 9. Controle de versão

- Versão: `v1-draft`
- Estado: `PENDENTE_APROVACAO_JURIDICO_DPO`
- Esta versão não autoriza deploy, migration de produção, uso de credenciais reais ou liberação comercial.
