# Gate Pré-Lançamento Comercial — V1

**Estado atual:** NÃO EXECUTÁVEL AINDA — o projeto está pré-comercial e o CNPJ/controlador comercial ainda não foi constituído.

Este documento não representa uma pendência da homologação atual. Ele é uma trava obrigatória de release: nenhuma versão poderá ser liberada para uso comercial enquanto todos os itens abaixo não estiverem concluídos e registrados.

## 1. Identidade e responsabilidade

- [ ] CNPJ constituído e identificado
- [ ] Razão social/nome empresarial registrados
- [ ] Controlador de dados identificado
- [ ] Responsável legal identificado
- [ ] Canal oficial de privacidade/titulares definido

## 2. Enquadramento LGPD / ANPD

- [ ] Reavaliar enquadramento como agente de tratamento de pequeno porte
- [ ] Avaliar critérios de tratamento de alto risco conforme regulamentação vigente
- [ ] Registrar decisão sobre necessidade ou dispensa de encarregado/DPO
- [ ] Se houver dispensa de encarregado, validar canal de comunicação com titulares

## 3. Inventário de tratamentos

- [ ] Mapear categorias reais de dados pessoais tratados
- [ ] Mapear titulares envolvidos
- [ ] Registrar finalidades de cada tratamento
- [ ] Registrar bases legais aplicáveis
- [ ] Identificar dados sensíveis, crianças/adolescentes/idosos, se houver
- [ ] Mapear decisões automatizadas relevantes
- [ ] Mapear compartilhamentos e transferências

## 4. Retenção e descarte de produção

- [ ] Definir prazo/fundamento para dados cadastrais
- [ ] Definir prazo/fundamento para pedidos e comandas
- [ ] Definir prazo/fundamento para dados financeiros/fiscais
- [ ] Definir prazo/fundamento para CRM/marketing
- [ ] Definir prazo/fundamento para auditoria e segurança
- [ ] Definir tratamento de backups e logs
- [ ] Definir anonimização/eliminações e exceções de conservação
- [ ] Publicar versão comercial da política de retenção

## 5. Direitos dos titulares

- [ ] Fluxo de acesso e confirmação de tratamento
- [ ] Correção
- [ ] Anonimização/bloqueio/eliminação quando cabível
- [ ] Portabilidade quando aplicável
- [ ] Revogação de consentimento
- [ ] Informação sobre compartilhamentos
- [ ] Processo para revisão de decisões automatizadas quando aplicável

## 6. Operadores, suboperadores e contratos

- [ ] Identificar provedores e operadores
- [ ] Definir responsabilidades contratuais
- [ ] Validar tratamento por OpenAI/IA, gateways, marketplaces, hospedagem, mensageria e demais terceiros efetivamente usados
- [ ] Validar transferências internacionais quando existirem
- [ ] Garantir segredos/credenciais fora do repositório

## 7. Segurança e incidentes

- [ ] Política comercial de segurança aprovada
- [ ] Controle de acesso/RBAC revalidado
- [ ] Segregação por tenant/unidade revalidada
- [ ] Logs sem PII/segredos excessivos
- [ ] Backup e restore de produção homologados em ambiente seguro
- [ ] Plano de resposta a incidentes definido
- [ ] Procedimento de comunicação de incidente compatível com regulamentação vigente

## 8. Release técnico

- [ ] Novo release candidate congelado
- [ ] Gate E reexecutado no ambiente de homologação
- [ ] Migration dry-run com esquema representativo
- [ ] Rollback testado
- [ ] Carga/concorrência representativas
- [ ] Caos/offline revalidado
- [ ] SLOs aprovados
- [ ] Acessibilidade revalidada
- [ ] Segurança/privacidade revalidadas

## 9. Decisões humanas obrigatórias

- [ ] Aprovação de governança de privacidade para produção
- [ ] Aprovação técnica de GO
- [ ] Aprovação humana separada para deploy
- [ ] Aprovação humana separada para migration de produção, se houver
- [ ] Aprovação humana separada para ativação de integrações/credenciais reais

## 10. Regra fail-closed

Se qualquer item obrigatório estiver incompleto, o estado deve permanecer:

`NO_GO_COMERCIAL`

Nenhuma automação, IA, CI ou workflow pode preencher automaticamente identidade legal, parecer jurídico, decisão de encarregado, aprovação de produção ou assinatura humana.

## 11. Referência regulatória atual

A Resolução CD/ANPD nº 2/2022 inclui pessoas naturais entre agentes de tratamento de pequeno porte e, para agentes elegíveis ao regime diferenciado, prevê dispensa de indicação de encarregado, sem afastar as demais obrigações da LGPD.

Referência oficial:

https://www.gov.br/anpd/pt-br/acesso-a-informacao/institucional/atos-normativos/regulamentacoes_anpd/resolucao-cd-anpd-no-2-de-27-de-janeiro-de-2022
