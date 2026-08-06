# Estabilização E2E da versão 1.0 no Windows

## Causa raiz

Os artefatos da falha no Windows mostravam o shell do Streamlit aberto, mas sem
`[data-testid="stTabs"]`; todos os dez cenários paravam no mesmo helper antes de
executar regras funcionais. O health endpoint confirma apenas que o servidor
HTTP está vivo. Ele não confirma que o WebSocket conectou, que os deltas Python
foram aplicados ou que o script terminou.

A prontidão estava, portanto, acoplada a um detalhe interno do DOM do Streamlit
(`stTabs`). Além disso, `reuseExistingServer` permitia reutilizar qualquer
processo saudável na porta 8501 e o launcher executava o binário `streamlit`
através de shell no Windows. Essa combinação não conseguia provar nem que a
página era a instância criada pela suíte nem que o aplicativo Python havia
terminado. Não foi encontrada evidência de dez regressões funcionais.

Na investigação local, o navegador abriu a URL configurada e o health endpoint
respondeu, o stdout do servidor ficou visível, o DOM funcional continha
`stApp`, `stMain`, `stMainBlockContainer` e as abas, e não houve `stException`.
A execução headed não era aplicável no contêiner sem XServer; a reprodução
headless preservou trace, screenshot e vídeo nas falhas. Os error contexts das
falhas de sincronização exibiram a interface funcional do PDV, sem traceback:
uma execução aguardava o `Tab` de um number input durante rerun e outra aguardava
um listbox que não abrira. Isso confirmou falhas de sincronização, não de regra
de negócio.

## Contrato final de prontidão

`waitForAppReady()` agora exige em conjunto:

1. navegação concluída até `domcontentloaded`;
2. exatamente um shell `stApp` e um `stMain`;
3. marcador próprio `data-fm-ai-e2e-ready="true"`, emitido no fim do script;
4. nenhum `stSkeleton` pendente;
5. nenhum `stException` e nenhum texto `Traceback`.

O helper não usa texto comercial, título, nome de aba, `stTabs` isoladamente ou
sleep fixo. Em timeout, registra título, URL, trecho do body, primeiros
`data-testid`, contagens dos elementos relevantes e contagem do marcador.

O marcador é um `span` invisível, sem dados sensíveis, protegido por
`is_test_mode()`. Ele só é emitido depois que todo o script Python construiu a
interface inicial e não altera a experiência de produção.

## Launcher e isolamento

- porta E2E exclusiva e previsível: `127.0.0.1:8517`;
- `reuseExistingServer: false`, portanto um processo anterior causa erro claro
  em vez de reutilização silenciosa;
- encerramento gracioso configurado no Playwright;
- launcher usa `python -m streamlit` sem shell, com `cwd` absoluto e `app.py`
  absoluto; `FM_AI_PYTHON`/`PYTHON` permitem selecionar explicitamente o venv;
- stdout e stderr são herdados e permanecem visíveis;
- `FM_AI_TEST_MODE=1`, `FM_AI_TEST_KEEP_TMP=1` e diretório temporário absoluto
  são propagados;
- o global setup recria e popula apenas
  `.tmp/fm-ai-playwright/fm_ai_test.sqlite3`; o launcher não reinicializa esse
  banco uma segunda vez;
- a configuração recusa colisão entre o caminho temporário e
  `banco_erp_local.db`.

## Como executar no Windows

No PowerShell, a partir da raiz do repositório:

```powershell
npm ci
npx playwright install chromium
$env:FM_AI_PYTHON = (Get-Command python).Source
npm run test:e2e -- --reporter=list
```

Se o browser corporativo já estiver instalado e o download do Playwright não
for possível, `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` pode apontar para o executável
do Chromium/Chrome. A suíte continua usando somente o projeto `chromium`.

## Diagnóstico

1. Confirme que nada ocupa `127.0.0.1:8517`; a suíte deve falhar claramente se
   houver colisão.
2. Verifique no stdout a URL/porta, o caminho impresso do banco temporário e
   qualquer traceback Python.
3. Consulte `test-results/**/error-context.md`, screenshot, vídeo e `trace.zip`.
4. A mensagem de timeout do helper inclui URL real, texto inicial, lista de
   `data-testid` e contagens de `stApp`, `stMain`, `stMainBlockContainer`,
   `stTabs`, `stSkeleton`, `stException` e do marcador próprio.
5. Consulte `/_stcore/health`, lembrando que HTTP saudável sozinho não significa
   aplicativo pronto.

## Resultados de estabilização

- smoke repetido: **3/3 passed**;
- specs isoladas: `functional-tabs` 1/1, `menu-engineering` 2/2,
  `pdv-cashback` 2/2 e `payments-stock-dashboard-bot` 4/4;
- suíte completa, primeira execução: **11 passed (6.5m)**;
- suíte completa, segunda execução consecutiva: **11 passed (6.7m)**;
- banco real: ausente no checkout antes e depois; somente o SQLite temporário
  absoluto foi criado e usado.

## Ruff

Os 14 achados reportados no Windows eram de higiene estática (imports e
`__all__` desordenados, `noqa` obsoletos, wildcard imports, exceção inadequada,
`dict()` desnecessário e datetime ingênuo proposital). Os contratos na base já
continham as correções específicas e passaram no gate direcionado; o gate de
formatação integral ainda revelou arquivos Python legados fora desse recorte.
Esses arquivos foram formatados pelo Ruff sem mudança intencional de regra de
negócio. A construção condicional da mensagem lateral foi escrita como `if/else`
explícito para evitar ambiguidade do transformador de comandos mágicos do
Streamlit após a formatação.

## Limitações e riscos conhecidos

O Streamlit atual emite avisos de depreciação de `use_container_width` e um
warning conhecido de estado/default do widget `pdv_cliente_id`. Eles não são
exceções, não afetam os gates e a troca ampla dessas APIs ficou fora do escopo de
estabilização. Máquinas lentas podem precisar do timeout de cenário de 120 s;
não foram introduzidos sleeps fixos. O rollback é a reversão deste único commit;
não há migration, mudança de schema ou alteração intencional de regra funcional.
