# V1 PAY-002 — PagBank PIX: runbook de homologação

## Estado

A infraestrutura financeira autoritativa está pronta para continuar a homologação real do PagBank:

- adapter Order/PIX com token injetado em memória;
- criação e consulta de `ORDE_...`;
- idempotência de criação;
- webhook HTTP dedicado em `/webhooks/pagbank`;
- validação criptográfica sobre o payload bruto antes de qualquer mutação;
- resolução multi-tenant pelo vínculo persistido `ORDE_... -> pagamento -> tenant/unidade`;
- referência de credencial armazenada no banco, nunca o token;
- reconciliação por consulta autenticada ao PagBank;
- finalizador canônico assíncrono compartilhado por webhook e reconciliação;
- snapshot durável do PDV pendente, independente da sessão do Streamlit;
- conclusão transacional de Pedido, Estoque, Venda Financeira e projeções legadas após pagamento eletrônico `PAGO` confiável;
- claim transacional `PENDENTE -> PROCESSANDO -> FINALIZADA` para impedir efeito econômico duplicado em corrida webhook × reconciliação;
- migration comercial `0009_pdv_authoritative_runtime_v1` para as estruturas de suporte do PDV/finalização;
- CLI administrativo para configurar a referência da credencial;
- CLI administrativo de smoke test sandbox.

**Ainda não considerar PAY-002 homologada comercialmente.** A homologação real está bloqueada até existir acesso a uma credencial válida do PagBank Sandbox. Sem essa credencial não há evidência real de criação de `ORDE_...`, QR PIX, consulta remota ou webhook público assinado. A tela do PDV também continua com o simulador PIX legado e não deve ser cortada para PagBank antes dessa prova.

## Regras de segurança

1. Nunca colocar o token PagBank no Git, no código, em issue, PR, screenshot ou conversa.
2. Nunca passar o token por argumento de linha de comando.
3. O banco armazena somente uma referência como `env:PAGBANK_TOKEN`.
4. Webhook sem `x-authenticity-token` válido não liquida pagamento.
5. Consulta ao provedor só liquida PIX quando o PagBank devolve estado efetivamente pago.
6. O cliente/HTTP request nunca escolhe `tenant_id` ou `unidade_id` do webhook.
7. Uma referência externa ambígua entre restaurantes falha fechada.
8. Falha na finalização canônica após um webhook confiável não pode deixar pagamento parcialmente confirmado: a transação deve sofrer rollback e o ingresso HTTP deve permitir retry.
9. Confirmação de PIX nunca deve depender de sessão aberta no navegador.

## 1. Preparar a branch

```powershell
cd C:\fm-ai-platform
git fetch origin
git switch impl/v1-wave1-authoritative-transactions
git pull --ff-only origin impl/v1-wave1-authoritative-transactions
```

## 2. Configurar o runtime

Para homologação local controlada:

```powershell
$env:FM_AI_ENV = "development"
$env:FM_AI_PAGBANK_ENV = "sandbox"
```

Em staging/produção, `DATABASE_URL`, `FM_AI_TENANT_ID` e `FM_AI_UNIDADE_ID` devem seguir o contrato comercial do runtime. Não usar SQLite comercial salvo em homologação controlada explicitamente autorizada.

## 3. Injetar o token sem gravá-lo no histórico

O valor deve existir somente no ambiente do processo que executará a homologação. Não usar `setx`, não colocar o token em arquivo versionado e nunca colar a credencial em conversa ou log.

Depois de carregar a variável, valide somente presença/comprimento sem imprimir o conteúdo. A credencial precisa ser realmente do ambiente Sandbox; credencial de Produção ou outro identificador não substitui o token Sandbox.

## 4. Registrar a referência segura no banco

O administrador precisa existir na identidade V1 e possuir `integracao.gerenciar`.

```powershell
python -m scripts.configure_pagbank_v1 --admin-email SEU_ADMIN@EMAIL.COM
```

A senha é pedida por `getpass`. O comando valida `PAGBANK_TOKEN` e persiste somente:

```text
provedor=pagbank
finalidade=api_token
referencia=env:PAGBANK_TOKEN
```

Rotacionar a configuração executando o mesmo comando novamente cria uma nova versão e desativa a referência anterior.

## 5. Provar comunicação real com o sandbox

Criar uma cobrança pequena de homologação:

```powershell
python -m scripts.pagbank_sandbox_smoke_v1 create --amount 1.00 --admin-email SEU_ADMIN@EMAIL.COM
```

O utilitário pede interativamente nome, e-mail e CPF/CNPJ do cliente de teste. Esses dados são usados na requisição e não são gravados no banco por esse smoke test.

Resultado obrigatório antes de avançar:

- `order_id` começando com `ORDE_`;
- status remoto retornado;
- PIX copia e cola e/ou URL de QR Code quando fornecidos pelo sandbox;
- nenhuma exposição do token.

Consultar novamente o pedido:

```powershell
python -m scripts.pagbank_sandbox_smoke_v1 consult --order-id ORDE_EXEMPLO --admin-email SEU_ADMIN@EMAIL.COM
```

A consulta é uma segunda fonte financeira confiável e independente do webhook.

**Estado atual desta etapa:** bloqueada externamente por indisponibilidade de uma credencial Sandbox válida. Não substituir por mock e não marcar como homologada.

## 6. Subir o ingresso HTTP do webhook

A API de integração é separada do Streamlit:

```powershell
python -m uvicorn http_api.app:build_http_app --factory --host 0.0.0.0 --port 8080
```

Healthcheck:

```text
GET /healthz
```

Webhook:

```text
POST /webhooks/pagbank
```

O endpoint deve ser publicado em HTTPS para o sandbox. O URL público configurado para novas cobranças deve terminar em `/webhooks/pagbank`.

Exemplo de configuração de ambiente, sem assumir um domínio específico:

```powershell
$env:FM_AI_PAGBANK_NOTIFICATION_URL = "https://SEU-ENDERECO-PUBLICO/webhooks/pagbank"
```

Reinicie o processo que cria cobranças depois de alterar essa variável.

## 7. Critérios de aceite do webhook

Uma homologação válida precisa provar:

- pedido conhecido + assinatura válida + status pago -> pagamento interno pode ser liquidado;
- assinatura ausente ou inválida -> `204`, nenhuma mutação financeira;
- `ORDE_...` desconhecido -> resposta neutra, nenhuma mutação;
- credencial do tenant/unidade ausente -> `503`, nenhuma mutação;
- referência externa ambígua -> falha fechada;
- replay do mesmo evento -> idempotente;
- payload acima do limite -> rejeitado;
- Outbox e auditoria acompanham a confirmação financeira;
- falha da finalização canônica -> nenhuma confirmação parcial e resposta retryable.

## 8. Reconciliação e finalização canônica assíncrona

Se o webhook atrasar ou não chegar, o sistema possui reconciliação por `GET` autenticado ao PagBank. A consulta não reutiliza a confiança do navegador nem confirmação humana: somente resposta remota com estado pago pode promover PIX.

Webhook assinado e reconciliação autenticada convergem para o mesmo finalizador canônico. Depois que o Pagamento fica `PAGO`, a mesma transação deve:

1. adquirir o trabalho durável de finalização exatamente uma vez;
2. promover Pedido de `AGUARDANDO_CONFIRMACAO` para `CONFIRMADO`;
3. consumir a reserva canônica de estoque usando o snapshot da venda;
4. reconhecer a Venda Financeira canônica;
5. executar as projeções legadas idempotentes de venda, estoque e cashback;
6. gravar o vínculo canônico ↔ legado;
7. atualizar a reconciliação do PDV;
8. marcar o trabalho como `FINALIZADA`.

O claim transacional e as chaves determinísticas tornam replay e corrida webhook × reconciliação seguros. Se qualquer etapa falhar, o commit não deve ocorrer; o evento pode ser tentado novamente sem aceitar efeito econômico parcial.

Essa orquestração já possui prova automatizada independente da credencial real. Isso **não substitui** a prova real dos passos 5–7.

## 9. Cutover do PDV

A tela atual do PDV ainda contém o simulador de PIX legado. O cutover visual só deve ocorrer depois dos passos reais de criação, consulta e webhook serem comprovados com Sandbox.

No cutover final:

1. selecionar PIX no PDV cria a obrigação canônica;
2. o backend cria a cobrança PagBank usando a referência de segredo do tenant/unidade;
3. a tela mostra o QR/copia-e-cola real retornado pelo PagBank;
4. Pedido permanece aguardando confirmação financeira;
5. webhook assinado ou reconciliação autenticada confirma o PIX;
6. o finalizador canônico conclui Pedido/Estoque/Venda/projeções sem depender do navegador;
7. erro de provedor nunca faz fallback para `PAGO` manual.

## Gate automatizado

O workflow permanente `V1 Wave1 Authoritative Transactions` compila e lint-a a borda HTTP, adapter PagBank, reconciliação, finalizador, migration e CLIs, executa os testes focados e a suíte Python completa.

O workflow `V1 Wave1 PDV Browser Gate` mantém a jornada canônica atual do PDV no Streamlit. Enquanto o PagBank real não estiver homologado, esse gate não deve ser descrito como E2E PIX real.

A automação não substitui a homologação real do Sandbox nem a validação humana final do PDV no navegador.
