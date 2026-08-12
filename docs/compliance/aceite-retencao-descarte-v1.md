# Registro de Governança — Retenção e Descarte de Dados V1

**Status atual:** CONCLUÍDO PARA HOMOLOGAÇÃO PRÉ-COMERCIAL

**Produção / uso comercial:** NÃO AUTORIZADOS POR ESTE REGISTRO

Este documento substitui a pendência genérica de “aceite jurídico/DPO” da fase de homologação por uma decisão de governança compatível com o estado real do projeto. Ele não é parecer jurídico, não simula assinatura de advogado ou encarregado e não autoriza produção.

## 1. Situação declarada do projeto

Em 12/08/2026, o titular do projeto declarou que:

- atua atualmente como **pessoa física**;
- o projeto está em fase de desenvolvimento e homologação, sem lançamento comercial;
- o CNPJ será constituído **antes de qualquer uso comercial dos produtos**.

O GitHub não foi usado para validar identidade civil, CNPJ inexistente ou qualificação profissional jurídica. O registro é uma declaração de governança do titular do projeto para o escopo pré-comercial.

## 2. Escopo desta decisão

Esta decisão cobre somente:

- desenvolvimento;
- testes automatizados;
- homologação técnica isolada;
- dados sintéticos ou anonimizados no ambiente de teste;
- evidências sem banco bruto, PII intencional, credenciais reais ou tráfego real de clientes.

O release candidate homologado permanece `cc6352d3ba6fbbed517faba82badadf719f5e36d`.

## 3. Decisão de governança

**Decisão:** `APROVADO_PARA_HOMOLOGACAO_PRE_COMERCIAL`

A política `docs/compliance/politica-retencao-descarte-v1.md`, versão `v1-pre-comercial`, fica adotada como política interna do projeto para a fase pré-comercial.

Não há pendência jurídica necessária para continuar desenvolvimento e homologação no escopo acima, porque o Gate E atual não utiliza dados de produção e não concede liberação comercial.

## 4. Tratamento como pessoa natural

A Resolução CD/ANPD nº 2/2022 inclui pessoas naturais no conceito de agentes de tratamento de pequeno porte quando assumem obrigações típicas de controlador ou operador. A mesma resolução prevê que agentes de pequeno porte, quando elegíveis ao regime diferenciado, não são obrigados a indicar encarregado, devendo manter canal de comunicação com titulares quando aplicável.

Esse enquadramento não é presumido para a futura operação comercial: deverá ser reavaliado conforme natureza, escala, receita, risco e tratamentos efetivamente realizados.

Referência oficial:

- Resolução CD/ANPD nº 2/2022 — https://www.gov.br/anpd/pt-br/acesso-a-informacao/institucional/atos-normativos/regulamentacoes_anpd/resolucao-cd-anpd-no-2-de-27-de-janeiro-de-2022

## 5. Regra obrigatória antes do lançamento comercial

Antes de qualquer deploy ou uso comercial, deverá ser cumprido integralmente o documento `docs/compliance/gate-pre-lancamento-comercial-v1.md`.

Entre as condições obrigatórias estão:

- constituição e identificação do CNPJ/controlador;
- definição do responsável legal pela governança de privacidade;
- reavaliação do enquadramento como agente de pequeno porte e de eventual tratamento de alto risco;
- definição das bases legais e finalidades reais de tratamento;
- definição dos prazos de retenção de produção por categoria;
- canal para titulares;
- contratos e responsabilidades com operadores/suboperadores;
- decisão documentada sobre necessidade ou dispensa de encarregado;
- nova validação de segurança, privacidade e Gate E para produção.

## 6. Efeito sobre o Gate E atual

O campo técnico `legal_approval=false` pode permanecer no Gate E de **produção**. Ele passa a representar um bloqueio de lançamento comercial por desenho, e não uma pendência da homologação pré-comercial.

Consequentemente:

- homologação pré-comercial: **CONCLUÍDA**;
- produção/comercialização: **BLOQUEADA POR POLÍTICA ATÉ O GATE PRÉ-LANÇAMENTO**;
- nenhum deploy, migration de produção, credencial real ou liberação comercial é autorizado por este documento.

## 7. Controle de versão

- Versão do registro: `v1-pre-comercial`
- Data: `2026-08-12`
- Responsável atual: titular pessoa física do projeto, identificado operacionalmente pela conta GitHub `faabio3131`
- Natureza: decisão interna de governança pré-comercial
- Parecer jurídico externo: não emitido / não simulado
