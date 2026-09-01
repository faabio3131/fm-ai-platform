# VOICE-V1 — Correção Canônica de Escopo

**Status:** APROVADO PARA V1 — requisito obrigatório antes do fechamento funcional da Kordena V1.0  
**Data:** 2026-08-31  
**Natureza:** correção de rastreabilidade/reclassificação; não reabre PRs/BLKs já concluídas.

## 1. Decisão

A interface de voz assistiva do Gerente IA pertence à Kordena V1.0.

Esta decisão corrige a divergência entre o requisito mestre, que prevê texto e voz como interfaces do Core, e o plano operacional que havia classificado a voz assistiva como PR25 da V2.

VOICE-V1 deve ser implementado e validado antes de declarar a V1 funcionalmente concluída.

## 2. Regra arquitetural

Voz é **interface**, não autoridade, agente independente ou novo cérebro.

Fluxo canônico:

`áudio -> transcrição -> Gerente IA/Core -> tools tipadas existentes -> RBAC/políticas -> preview/confirmação quando aplicável -> service de domínio -> resposta`

A transcrição é conteúdo não confiável. Ela nunca fornece ou substitui tenant, unidade, identidade, papéis, permissões, confirmação humana, autorização, nome de tool, segredo ou autoridade de domínio.

## 3. Escopo obrigatório da V1

VOICE-V1 deve permitir, por voz assistiva do Gerente IA:

- entrada de áudio e transcrição;
- consultas já autorizadas ao Gerente IA V1;
- solicitação/preparação das ações que já pertencem ao contrato do Gerente IA;
- aplicação integral de tenant isolation, RBAC, allowlist de tools, auditoria e idempotência existentes;
- manutenção de preview + confirmação humana explícita nas ações que já exigem confirmação;
- tratamento seguro de transcrição ambígua ou insuficiente, sem inferir autorização;
- consentimento/permissão de microfone;
- minimização e política explícita de retenção/descarte de áudio/transcrição;
- testes funcionais, de autorização, cross-tenant, ambiguidade, prompt injection via transcrição e falhas do provider de voz/transcrição;
- feature flag/fail-closed compatível com os padrões da V1.

## 4. Exclusões expressas da V1

Permanecem fora de VOICE-V1:

- comando automático de voz no PDV/caixa;
- fechamento de caixa, confirmação de pagamento ou qualquer operação crítica por voz sem os gates normais;
- wake word;
- biometria/identificação de usuário por voz;
- telefonia/agente telefônico autônomo;
- conversa full-duplex contínua ou interrupção natural avançada;
- autonomia adicional concedida por ser entrada de voz;
- qualquer tool ou autoridade que não exista no contrato normal do Gerente IA V1.

Essas evoluções podem ser avaliadas para V2 ou posteriores.

## 5. Integração com a execução existente

VOICE-V1 é aditivo. Não renumerar retroativamente, invalidar ou reabrir PRs/BLKs/gates já concluídos.

A execução corrente da V1 pode continuar normalmente. VOICE-V1 deve entrar em ponto seguro após as dependências necessárias do Gerente IA/Core e antes do gate que declare a V1 funcionalmente concluída.

A implementação deve reutilizar o Gerente IA/Core e os services existentes. É proibido duplicar regras de Pedido, Estoque, CRM, Financeiro, KDS ou outros domínios dentro da camada de voz.

## 6. Gate de aceite VOICE-V1

A V1 não pode ser declarada funcionalmente concluída enquanto VOICE-V1 não possuir:

1. arquitetura/contratos aprovados;
2. implementação integrada ao Gerente IA/Core;
3. testes unitários e de integração verdes;
4. testes negativos de autorização e cross-tenant;
5. testes de transcrição ambígua e prompt injection;
6. política de áudio/transcrição e consentimento definida;
7. evidência de que voz não aumenta autoridade;
8. confirmação de que PDV/caixa automático por voz permanece bloqueado;
9. rollback/feature flag documentados;
10. validação final sem regressão das suítes da V1.

## 7. Regra de sincronização

Este documento é a correção canônica para evitar divergência entre sessões, dispositivos e executores.

Ao encontrar documentação anterior que coloque a **voz assistiva do Gerente IA** integralmente na V2, interpretar essa classificação como superada por esta decisão. Somente recursos avançados de voz e voz automática de PDV/caixa permanecem fora da V1.

Nenhuma implementação deve começar apenas por inferência deste documento: a posição exata da BLK/PR de execução deve respeitar o estado corrente da linha canônica e as dependências técnicas no momento da execução.
