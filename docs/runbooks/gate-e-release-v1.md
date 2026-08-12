# Runbook Gate E — homologação, go/no-go e rollback V1

## Objetivo e autoridade

Este runbook organiza a evidência final da V1. Ele **não autoriza** deploy,
migration ou acesso a produção. A execução real exige owner técnico/operacional,
janela aprovada e autorização humana separada.

## Pré-condições

- commit/release candidate imutável identificado por SHA;
- todos os workflows da PR candidatos verdes;
- tenant/unidade de homologação isolados;
- credenciais de teste em cofre, nunca no repositório/log;
- inventário de integrações e feature flags congelado;
- owner, observador e responsável por rollback definidos;
- cópia de dados anonimizada quando dados realistas forem necessários.

## 1. Backup e baseline

1. Registrar engine/versão, tamanho e horário UTC.
2. Gerar backup consistente e criptografado.
3. Registrar SHA-256 do artefato de backup.
4. Gerar baseline sem PII com contagens, somas financeiras em centavos e checksum
   por faixas estáveis de IDs/saldos.
5. Registrar RPO medido entre checkpoint e backup.

**Bloqueio:** backup sem hash, sem owner, não restaurável ou com PII desnecessária.

## 2. Restore obrigatório

1. Restaurar **somente** em ambiente isolado/efêmero autorizado.
2. Medir o RTO do início da restauração até aplicação pronta para validação.
3. Recalcular contagens, somas e checksums.
4. Comparar 100% com o baseline.
5. Executar smoke/read-only dos relatórios e projeções.

**Aceite:** RTO <= 30 min, RPO <= 5 min e zero divergência de contagem, soma ou
checksum. Qualquer divergência é NO-GO.

## 3. Migration dry-run

A migration real continua fora desta PR. Quando houver migration autorizada:

1. usar cópia anonimizada/efêmera;
2. medir duração e locks;
3. executar upgrade;
4. validar nulos/órfãos, somas e checksums;
5. ensaiar rollback lógico por feature flag/rota;
6. quando houver downgrade técnico, ele deve ser não destrutivo;
7. registrar artefatos antes/depois e hashes.

URL remota/produção, credencial embutida ou operação destrutiva sem procedimento
humano aprovado aborta a execução.

## 4. Carga

Executar pico representativo de pedidos simultâneos por PDV, salão e delivery com
produção/KDS e eventos ativos. Medir:

- throughput;
- p50/p95/p99;
- disponibilidade e taxa de erro;
- saturação de CPU/memória/conexões;
- backlog de outbox/inbox/DLQ;
- duplicidade de pedido, Venda, baixa, cashback e impressão.

A janela e o volume precisam constar no artefato. Nenhum threshold é alterado
durante o teste para transformar falha em aprovação.

## 5. Caos/offline

Executar, um cenário por vez:

- KDS offline e retorno;
- impressora indisponível e reconexão;
- marketplace indisponível/timeout;
- gateway financeiro indisponível sem promover pagamento;
- event bus/fila indisponível com retry e DLQ;
- reinício de worker durante retry/reconciliação.

O sistema deve falhar fechado quando não possui autoridade externa e degradar com
segurança quando houver contingência definida. São bloqueadores: perda de dados,
efeito duplicado, estado financeiro inventado, quebra de tenant ou recuperação
acima do orçamento definido.

## 6. Segurança

Executar novamente:

- IDOR e isolamento multiempresa;
- matriz RBAC e alçadas;
- replay/idempotência;
- CSRF/entrada inválida quando aplicável;
- prompt injection para Mica/Gerente IA;
- segredo/token/credencial em logs e artefatos;
- acesso direto indevido a SQL/ORM por adapters/IA;
- ação crítica sem confirmação humana.

Achado crítico/alto aberto é NO-GO.

## 7. LGPD e privacidade

- validar minimização por finalidade;
- confirmar marketing negado por padrão para marketplace;
- confirmar opt-out imediato e re-opt-in explícito;
- inspecionar logs, eventos, DLQ, traces e auditoria para PII/segredos;
- validar anonimização da cópia de homologação;
- confirmar retenção e descarte com responsável jurídico/DPO.

A validação jurídica/DPO é uma dependência externa; CI não substitui esse aceite.

## 8. Acessibilidade

Executar E2E por teclado e viewport móvel nas jornadas críticas. Verificar:

- nome acessível em botões/campos;
- foco visível e ordem de tabulação;
- operação sem mouse nas ações principais;
- mensagens de erro/estado compreensíveis sem depender só de cor;
- zoom/layout sem perda de ação essencial.

Falha que impeça jornada crítica é bloqueadora.

## 9. SLO

Gerar amostra da mesma release candidate e comparar com o baseline V1:

- disponibilidade >= 99,5%;
- p95 <= 1.500 ms;
- erro <= 1,0%;
- DLQ backlog = 0 no momento do gate;
- item mais antigo da DLQ <= 15 min;
- RTO <= 30 min;
- RPO <= 5 min.

Registrar janela, volume, infraestrutura e SHA da aplicação. Ajuste de SLO exige
nova decisão humana documentada, nunca edição oportunista durante o gate.

## 10. Go/No-Go

**GO** somente quando todos os onze tipos de evidência do Gate E estiverem:
aprovados, não expirados, com artefato SHA-256 e nível de homologação/produção.

**NO-GO** se qualquer item estiver ausente/reprovado/expirado, se restore divergir,
SLO falhar, caos perder/duplicar efeito, houver falha crítica de segurança/LGPD ou
runbook/rollback não tiver responsável.

A decisão final precisa registrar participantes, horário UTC, SHA da release e
bloqueios/avisos. O software não aprova sozinho a própria liberação.

## 11. Rollback

Se um limite for excedido após canary:

1. interromper expansão da coorte;
2. desabilitar a feature flag/rota autoritativa afetada;
3. preservar dados novos, sem hard delete;
4. drenar/reconciliar outbox/inbox/DLQ;
5. compensar efeitos confirmados por comandos idempotentes;
6. comparar novamente vendas, pagamentos, estoque e cashback;
7. registrar incidente, timeline e correlation IDs;
8. só retomar após causa e evidência de correção.

Nunca usar rollback para apagar silenciosamente dados operacionais ou reverter
movimentos financeiros/estoque por edição direta.
