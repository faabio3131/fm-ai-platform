# Kordena — certificação diagnóstica de carga com IA (2026-10-16)

**Decisão:** fluxo operacional sem IA testado com êxito, **capacidade do Gerente IA NÃO CERTIFICADA sob concorrência**. O workflow pode terminar verde por medir e registrar corretamente um resultado operacional reprovado.

## Evidências
- Runner: https://github.com/faabio3131/fm-ai-platform/actions/runs/38917093820
- Artefatos JSON: https://github.com/faabio3131/fm-ai-platform/actions/runs/38917093820/artifacts/12054040371
- HEAD dos testes: `a32c567425501625bf332ef8c689a876b2aba2cd`
- Branch segregada: `bench/kordena-core-capacity-20261016`.
- Nenhum merge, deploy, segredo real, tráfego de carga na produção ou chamada paga de IA.

## Histórico do ambiente publicado
Em 32 respostas HTTP 200 do simulador do assistente na Railway (13/10), mediana 8,05 s, média 7,83 s, p95 12,27 s, máximo 15,37 s. Esses tempos medem o **HTTP inteiro**, não o provedor isoladamente. Healthchecks reais mínimos: OpenAI 3,04 s; Gemini 2,58 e 3,44 s. Um acesso de saúde ao backend não equivale a chamada de IA.

## Caminho operacional sem LLM
`/v1/gerente-ia/tools` com autenticação, Postgres 16 isolado, consulta operacional e persistência de auditoria: em concorrência HTTP 500, 500/500 HTTP 200, p95 3,22 s, throughput 91,28 RPS; sustentado em 50 in-flight, 2.500/2.500 HTTP 200, p95 739,7 ms, 87,44 RPS. Resultados em runner ASGI in-process **não representam capacidade da Railway**.

## Caminho de perguntas com latência artificial de LLM
`/v1/gerente-ia/perguntar`: FastAPI, SSO, UoW, tools e metering durável efetivos, PostgreSQL 16 efêmero; somente a **espera de inferência simulada**: 3,0 s. Pool SQLAlchemy do experimento: 10 conexões base + 10 overflow, timeout 8s. **0 chamadas aos provedores**.

| Concorrência em voo | Req. | HTTP 200 | HTTP 503 | p95 geral | Pico de conexões |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 2 | 2 | 0 | 3,02 s | 2 |
| 5 | 10 | 10 | 0 | 3,07 s | 7 |
| 10 | 20 | 20 | 0 | 3,15 s | 19 |
| 25 | 35 | **28** | **7** | **11,29 s** | **20 de 20** |

A sequência foi interrompida no orçamento de erros; **não houve teste de 100/250/500 perguntas de IA**, portanto esses patamares NÃO foram aprovados.

### Fallback controlado
Primária aguarda 0,7 s e falha transitoriamente; fallback aguarda 2 s:
- 1 in-flight: 2/2 HTTP 200, p95 2,72 s.
- 10 in-flight: 20/20 HTTP 200, p95 2,87 s; pico de 20 conexões.
- 50 in-flight: **18/50 HTTP 200, 32/50 HTTP 503**, p95 **17,75 s**, pico **20/20**.

## Diagnóstico comprovado
Instrumentação do handler: `sqlalchemy.exc.TimeoutError` nas falhas 503; observabilidade do pool: **20/20 conexões ocupadas**. O fluxo em `application/gerente_ia_web.py` e `application/gerente_ia_runtime.py` consulta a IA de modo bloqueante durante o escopo da UoW, enquanto `infra/ai_metering.py` abre transação independente. Essa combinação reproduziu contenção no cenário isolado. **O limite de 20 conexões foi configurado no benchmark; não se pode atribuí-lo à Railway sem verificação.**

Outros riscos de engenharia identificados mas ainda não isolados causalmente: uma réplica no serviço Railway, gateway Gemini efêmero com até 4 tentativas, tratamento `async` de áudio chamando código síncrono, tracing Railway não habilitado.

## Próximos gates
1. Separar rede/IA do ciclo transacional do banco com revalidação de tenant, versão, autorizações e idempotência ao retomar; não enfraquecer atomicidade.
2. Cliente de provider verdadeiramente não bloqueante ou execução segregada, deadline end-to-end, orçamentos de tentativas, circuit breakers, backpressure e cotas por tenant.
3. Metering durável independente sem disputa crítica pelo pool de negócio, com entrega garantida e reconciliação.
4. Instrumentar tempo de provedor/planejamento/DB/filas, conexões ocupadas, p50/p95/p99, 429/503, custo/tokens e falhas/fallback.
5. Repetir benchmark após correção, depois piloto de **poucas chamadas reais** OpenAI/Gemini com teto de custo e autorização governada, e finalmente ensaio multi-tenant em ambiente equivalente à produção.

**Sem aprovação:** capacidade de alto fluxo comercial com IA; extrapolações de ASGI runner para Railway; equivalência entre requisições em voo e usuários reais.
