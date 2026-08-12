# Hardening transversal V1 — PR21 / Gate E

## Objetivo

Fechar a expansão operacional da V1 com um gate final **fail-closed**. A PR21 não
transforma CI verde em autorização de produção: ela cria contratos, testes e
runbooks para decidir quando a plataforma está pronta para homologação e, depois,
quando há evidência suficiente para um go/no-go de release.

A arquitetura exige no Gate E: carga, caos/offline, segurança, privacidade,
acessibilidade, migração/restore, SLOs e runbooks. Também exige que migração e
rollback sejam ensaiados com reconciliação sem perda/destruição.

> **Evidência sintética não autoriza release.** O CI desta PR pode aprovar a
> preparação para homologação, mas o release permanece NO-GO até existirem
> evidências válidas de homologação ou produção para todos os itens obrigatórios.

## Contratos implementados

`core/hardening` contém uma camada pura, sem ORM, HTTP ou import do `app.py`:

- `MetasSloV1` e `AmostraSlo`: baseline de disponibilidade, latência p95, taxa de
  erro, DLQ, RTO e RPO;
- `SnapshotIntegridade`: contagens, somas em centavos e checksums sem PII;
- `comparar_restore`: exige igualdade do baseline antes/depois do restore;
- `ResultadoCaos`: reprova perda de dados, efeito duplicado, ausência de
  recuperação ou recuperação acima do orçamento;
- `EvidenciaGateE`: artefato versionado por SHA-256, nível, validade e tipo;
- `avaliar_pronto_para_homologacao`: aceita evidência sintética verde, mas retorna
  aviso explícito de que ainda não é release;
- `avaliar_release`: exige evidência de homologação ou produção para **todos** os
  tipos do Gate E;
- guarda de privacidade para payloads de observabilidade/auditoria;
- guarda de ambiente que bloqueia URL de banco remota, gerenciada ou com
  credencial embutida em scripts de teste/restore.

## Evidências obrigatórias do Gate E

O avaliador exige os onze grupos abaixo, sem exceção silenciosa:

1. suíte de testes;
2. carga/concorrência;
3. caos/offline;
4. segurança;
5. privacidade/LGPD;
6. acessibilidade;
7. restore;
8. rollback;
9. SLO;
10. runbook;
11. migration dry-run.

Evidência ausente, reprovada, expirada ou de nível insuficiente produz NO-GO.

## Baseline inicial de SLO para homologação

Os números abaixo são um baseline operacional inicial da V1 e **não substituem o
aceite do owner antes de produção**:

| Indicador | Meta inicial |
|---|---:|
| Disponibilidade | >= 99,5% |
| Latência p95 | <= 1.500 ms |
| Taxa de erro | <= 1,0% |
| Backlog DLQ | 0 no momento do gate |
| Idade do item mais antigo da DLQ | <= 15 min |
| RTO | <= 30 min |
| RPO | <= 5 min |

Amostra real de homologação deve indicar janela, volume, versão do código,
infraestrutura, tenant/unidade de teste e artefato imutável usado como prova.

## Carga e concorrência

A PR21 adiciona carga sintética sobre o fluxo de Delivery: 128 tentativas
concorrentes de mutar a **mesma versão** do carrinho. O aceite é exatamente uma
mutação vencedora e 127 conflitos de concorrência; quantidade, subtotal e efeitos
permanecem únicos. Isso reforça o contrato de CAS sem depender de relógio/latência
frágil no CI.

Em homologação, a carga deve incluir pico de pedidos simultâneos, KDS, salão,
pagamentos simulados, delivery e consumo de eventos, medindo p50/p95/p99, taxa de
erro, backlog, saturação e tempo de recuperação.

## Caos e operação offline

Os cenários mínimos de homologação são:

- KDS sem conectividade: operação degradada segura, sem perder nem duplicar item;
- impressora indisponível/reconecta: KDS continua padrão e ticket não duplica;
- marketplace/gateway indisponível: fail-closed onde não há autoridade para
  confirmar estado externo;
- fila/event bus indisponível: outbox/inbox preservam idempotência, retry e DLQ;
- reinício durante retry/reconciliação: nenhum pedido, venda, baixa ou cashback é
  duplicado.

Todo cenário registra falha injetada, modo esperado, efeitos, perda/duplicidade,
tempo de recuperação e artefato de evidência.

## Restore, migração e rollback

O snapshot de integridade não transporta PII. Ele compara, no mínimo:

- contagem de vendas, pedidos, clientes e movimentos relevantes;
- somas financeiras em centavos por período/método;
- checksums por faixas estáveis de IDs e saldos de estoque/cashback.

Restore só é aprovado se contagens, somas e checksums forem iguais. Migration
dry-run deve acontecer em banco efêmero/cópia anonimizada e o destino é bloqueado
por padrão se for remoto/produção. Rollback desliga flags/rota nova, preserva dados
novos legíveis e reconcilia efeitos já confirmados; não existe downgrade destrutivo
automático.

## Segurança e LGPD

O Gate E exige repetir testes negativos de tenant/IDOR/RBAC, segredos, prompt
injection e ações críticas. Payloads de log/auditoria não podem conter telefone,
e-mail, endereço, documento, senha, token, autorização, client secret, mensagens
ou payload bruto. Referências opacas e hashes explícitos são permitidos.

Cópia de homologação deve ser anonimizada. Retenção e anonimização final precisam
de validação jurídica/DPO; a PR não declara política legal definitiva.

## Acessibilidade

Antes do release, os E2E por papel devem ser executados também em viewport móvel e
teclado. Controles críticos precisam de nome acessível, foco visível e ordem de
tabulação utilizável; informação de erro/estado não pode depender somente de cor.
A evidência de acessibilidade é item obrigatório do Gate E e não pode ser
substituída por uma declaração manual sem artefato.

## Estado desta PR

O CI da PR21 produz somente **evidência sintética**. Nenhum teste desta PR toca
banco ou credencial real. Não há deploy, migration real, restore de produção,
tráfego real de marketplace/gateway, alteração fiscal/contábil ou ativação global
de feature flag.

Consequentemente, mesmo com todos os testes verdes, o estado de produção continua
**NO-GO** até a execução do runbook em homologação e aprovação humana explícita.
