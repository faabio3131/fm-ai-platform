# Arquitetura operacional — FM AI Platform 1.0

**Status:** projeto executivo, sem implementação ou migração.  
**Documentos normativos complementares:** [máquinas de estado](maquinas-de-estado-v1.md), [migração](plano-migracao-pedidos-v1.md) e [plano de PRs](plano-prs-operacao-v1.md).

## 1. Visão do produto

A versão 1.0 será uma plataforma operacional de restaurante em que **Pedido** é o agregado central. Canais (PDV, salão, delivery, Mica e marketplaces) criam o mesmo contrato; produção, pagamento, estoque, entrega e venda reagem ao pedido sem se confundirem com ele.

```text
Canal -> Carrinho/Comanda -> PEDIDO -> Produção/KDS -> Expedição/Entrega
                              |  |             |
                              |  +-> Estoque <-+
                              +----> Pagamento ----> Venda/Financeiro
                              +----> Eventos/Auditoria/CRM
```

**Regra inegociável:** produção e pagamento são processos independentes, coordenados por política de canal. Pagamento posterior não impede produção quando a política permitir. Venda é consequência financeira e só é concluída após pagamento confirmado, comanda fechada ou confirmação auditada de recebimento posterior por responsável autorizado.

## 2. Princípios arquiteturais

1. Agregado `Pedido` como fonte operacional; `Venda` não representa carrinho nem fila de cozinha.
2. Máquinas de estado independentes e transições explícitas, autorizadas e auditadas.
3. Política de liberação para cozinha determinística, versionada e testável.
4. Valores em `Numeric(14,2)`/`Decimal`, quantidades em `Numeric(14,4)`, horários UTC e IDs UUID/ULID.
5. Multiempresa obrigatório: `empresa_id` derivado da identidade autenticada, nunca apenas do cliente; todo índice/único inclui o tenant quando aplicável.
6. Transação local + outbox; consumidores idempotentes; integrações por adapters anticorrupção.
7. Append-only para eventos, pagamentos, estoque e auditoria; correções por movimento compensatório.
8. Menor privilégio, segregação de funções e confirmação reforçada em ações críticas.
9. LGPD por finalidade, minimização, consentimento comprovável e exclusão/anônimização controlada.
10. Evolução aditiva, feature flags, compatibilidade com `Venda` legada e rollback sem perda.

## 3. Limites da versão 1.0

Inclui contratos e operação de pedido, produção/KDS, salão/comanda, balcão/retirada, delivery próprio, expedição, pagamentos, estoque, adapters iniciais, consentimento, Mica modular e consultas/ações controladas do Gerente IA. Não inclui nesta tarefa: tabelas, migrations, endpoints, mudança de UI ou de comportamento, integração real com adquirentes/marketplaces, fiscal/contábil completo, roteirização avançada ou comando de voz no PDV/caixa.

## 4. Auditoria: fluxo atual e futuro

### 4.1 Diagnóstico do código atual

| Área | Existe e pode ser reaproveitado | Acoplamento/refatoração necessária | Risco/compatibilidade |
|---|---|---|---|
| Aplicação | Streamlit monolítico em `app.py`, abas de cardápio, CRM, PDV, estoque, dashboard e Mica | ORM, UI, regra, integrações e transação estão no mesmo arquivo; extrair endpoints/schemas/services/repositories/models gradualmente | Importar `app.py` cria tabelas; proteger bootstrap e preservar SQLite atual |
| Modelos | `Usuario`, `Cliente`, `Produto`, `Insumo`, `FichaTecnica`, `Venda`, gateways e contatos | Ausência de tenant, pedido, itens, ledger, auditoria e relações operacionais | IDs inteiros e `Float`; manter colunas e linhas legadas, adicionar vínculos nulos inicialmente |
| PDV | validação monetária, troco, cliente balcão, cashback, estoque e reset em `pdv_utils.py` | Finalização cria `Venda`, baixa estoque e cashback na mesma transação; um produto por venda | Reexecução/concorrência e dupla baixa; adapter legado deve preservar relatórios |
| Pagamento/Pix | QR simulado e configuração; produção exige confirmação Pix no PDV | Configuração e credenciais em tabelas/UI; não há cobrança/transação/webhook/reconciliação | Não tratar QR exibido como pagamento; segredos devem ir a cofre e ser mascarados |
| Estoque/ficha | insumos, saldo, mínimo, validade, CMV e consumo por ficha | Saldo mutável e baixa direta na Venda/Mica, sem reserva, ledger ou lock | Corridas e baixa parcial/duplicada; snapshot da ficha no item futuro |
| Cliente/CRM | cadastro por WhatsApp, inatividade, cashback e mensagens | Consentimento não modelado; saldo cashback mutável e campanha junto da UI | WhatsApp é dado pessoal; clientes legados ficam sem opt-in até regularização |
| Mica | texto, imagem/áudio, JSON de itens, forma de pagamento, total, cliente e integração de teste | Conversa, inferência, venda, estoque e Pix num fluxo; fallback inventa produto e busca o primeiro; não há sessão/confirmação | Venda/pagamento falsamente aprovados, item errado e baixa apenas do último produto |
| Dashboard | soma Venda, CMV, lucro e histórico | Assume toda Venda como receita concluída | Visões compatíveis devem distinguir legado, competência e recebido |
| WhatsApp/Gemini | gateway Gemini centralizado, erros seguros e mocks; WhatsApp de teste | Chamadas e prompts ainda na UI; envio real e consentimento sem camada própria | Retentativa, PII, arquivos temporários e limites externos |
| Gerente IA/módulos | arquivos `core/gerente_ai.py` e `modulos/food/*` são placeholders | Definir tools tipadas e autorização no serviço, sem acesso direto ao banco | Prompt injection e ação crítica sem confirmação |
| Testes | unitários para PDV/Gemini/test mode, integração SQLite isolada e Playwright serial | Cobertura concentrada no monólito; faltam contratos, estados, concorrência, idempotência e autorização | Fixtures recriam schema manual; evoluir sem tocar banco real |

### 4.2 Fluxos

```text
ATUAL: entrada -> validações na UI -> Venda(Aprovado) + estoque + cashback -> dashboard
FUTURO: entrada -> conversa/carrinho -> Pedido confirmado -> regra de cozinha
        -> Produção (independente)                    -> entrega/serviço
        -> Pagamento (independente) -> critério financeiro -> Venda
        -> outbox -> estoque, KDS, CRM, auditoria, projeções
```

## 5. Modelo central de Pedido

`Pedido` guarda canal, cliente/comanda/endereço opcionais, valores congelados, políticas aplicadas e estados agregados. Alterações após confirmação são comandos (adicionar/remover/cancelar item), nunca edição silenciosa. `versao` implementa concorrência otimista; `numero` é legível e único por empresa/unidade/série.

### 5.1 Convenções comuns das entidades propostas

Todos os registros operacionais têm `id UUID PK`, `empresa_id UUID NOT NULL`, `criado_em timestamptz NOT NULL`, `atualizado_em timestamptz NOT NULL`, e quando mutáveis `versao int NOT NULL`. FKs usam `RESTRICT`; dados históricos não recebem cascade delete. Exclusão operacional é lógica (`arquivado_em`/`ativo`); evento, transação, movimento e auditoria são imutáveis. PII é criptografada/mascarada. Retenção padrão: fiscal/financeiro conforme obrigação legal; auditoria 5 anos (configurável); conversa 180 dias; payload bruto de integração 90 dias; consentimento durante a relação mais prazo probatório. A política final deve ser validada pelo jurídico/DPO.

### 5.2 Dicionário de entidades

Em `O?`, `N` significa NOT NULL e `S` opcional. Além dos campos comuns:

| Entidade / responsabilidade | Campos sugeridos (`tipo`, O?) | Índices, únicos e relações | Exclusão, sensibilidade, retenção e auditoria |
|---|---|---|---|
| **Pedido** — agregado operacional | `unidade_id uuid N`, `numero bigint N`, `canal enum N`, `status enum N`, `status_pagamento enum N`, `cliente_id uuid S`, `comanda_id uuid S`, `endereco_id uuid S`, `moeda char(3) N`, `subtotal/desconto/taxa/total numeric(14,2) N`, `politica_versao varchar N`, `risco enum N`, `confirmado_em/concluido_em/cancelado_em timestamptz S`, `criado_por uuid N` | UQ `(empresa_id,unidade_id,numero)`; IDX `(empresa_id,status,criado_em)`, cliente, comanda; 1:N itens/eventos/pagamentos/produção, 0:1 entrega, 0:N vendas | Não excluir confirmado; PII indireta; retenção fiscal; toda transição auditada |
| **PedidoItem** — snapshot vendável | `pedido_id uuid N`, `produto_id uuid S`, `sku/nome varchar N`, `quantidade numeric(14,4) N`, `preco_unitario/desconto/total numeric N`, `status enum N`, `setor_id uuid S`, `ficha_versao varchar S` | IDX pedido/status e setor; UQ `(pedido_id,sequencia)`; N:1 pedido/produto, 1:N adicionais/produção | Sem hard delete após confirmação; observações podem conter PII; auditar alterações |
| **PedidoItemAdicional** — modificador snapshot | `pedido_item_id uuid N`, `produto_adicional_id uuid S`, `grupo/nome varchar N`, `quantidade numeric N`, `preco_unitario/total numeric N`, `produzivel bool N` | IDX item; UQ `(pedido_item_id,sequencia)`; N:1 item | Mesmas regras do item; retenção com pedido |
| **PedidoEvento** — histórico/outbox do agregado | `pedido_id uuid N`, `tipo varchar N`, `versao_agregado int N`, `payload jsonb N`, `idempotency_key varchar N`, `ocorrido_em timestamptz N`, `ator_id uuid S`, `correlation_id uuid N`, `publicado_em timestamptz S`, `tentativas int N` | UQ `(empresa_id,idempotency_key)` e `(pedido_id,versao_agregado)`; IDX não publicados | Append-only; payload minimizado; retenção/auditoria longa |
| **PedidoObservacao** — instrução categorizada | `pedido_id uuid N`, `pedido_item_id uuid S`, `tipo enum N`, `texto text N`, `visibilidade enum N`, `autor_id uuid N` | IDX pedido/item/tipo; N:1 pedido/item | Soft delete antes da produção; texto potencialmente sensível; auditar leitura restrita/alteração |
| **Pagamento** — obrigação e consolidação | `pedido_id uuid N`, `comanda_id uuid S`, `status enum N`, `metodo enum N`, `valor_previsto/pago/estornado numeric N`, `vencimento timestamptz S`, `provedor varchar S`, `recebimento_posterior bool N` | IDX pedido/status, comanda; UQ chave lógica por parcela; 1:N transações | Não excluir; financeiro sensível; retenção legal; toda decisão auditada |
| **TransacaoPagamento** — tentativa imutável | `pagamento_id uuid N`, `tipo enum N`, `status enum N`, `valor numeric N`, `provedor varchar N`, `id_externo varchar S`, `idempotency_key varchar N`, `payload_resumo jsonb S`, `processada_em timestamptz S` | UQ `(empresa_id,idempotency_key)` e parcial `(provedor,id_externo)`; IDX pagamento/status | Append-only, compensar por nova transação; token/PCI nunca persistido; retenção financeira |
| **Venda** — consequência financeira (e legado) | novos: `pedido_id uuid S`, `comanda_id uuid S`, `status enum N`, `origem enum N`, `valor_bruto/liquido numeric S`, `reconhecida_em timestamptz S`; colunas atuais preservadas | IDX pedido, data/status; UQ opcional `(empresa_id,pedido_id,tipo)`; pedido 0:N venda | Venda legada permanece; imutável após fechamento salvo ajustes auditados |
| **Mesa** — recurso físico | `unidade_id uuid N`, `codigo varchar N`, `nome varchar S`, `capacidade int N`, `status enum N`, `posicao_x/y numeric S`, `ativo bool N` | UQ `(empresa_id,unidade_id,codigo)`; IDX status; 1:N comandas | Só desativar; sem PII; auditar mapa/status manual |
| **Comanda** — ciclo financeiro do salão | `mesa_id uuid S`, `numero varchar N`, `status enum N`, `responsavel_id uuid N`, `aberta_em/fechada_em timestamptz`, `total numeric N`, `versao int N` | UQ aberta `(empresa_id,numero)`; IDX mesa/status; 1:N pedidos/participantes/pagamentos | Não excluir após consumo; retenção financeira; transferências/divisões auditadas |
| **ComandaParticipante** — pessoa/divisão | `comanda_id uuid N`, `cliente_id uuid S`, `apelido varchar S`, `quota numeric S`, `ordem int N` | UQ `(comanda_id,ordem)`; IDX cliente; N:1 comanda | Anonimizar quando permitido; PII; histórico com fechamento |
| **UsuarioOperacional** — identidade/RBAC | `usuario_id uuid N`, `unidade_id uuid S`, `nome_exibicao varchar N`, `status enum N`, `mfa bool N`, `ultimo_acesso timestamptz S` | UQ `(empresa_id,usuario_id,unidade_id)`; IDX status; N:M papéis | Desativar, nunca apagar ações; PII; auditar login/permissão |
| **Garcom** — perfil operacional | `usuario_operacional_id uuid N`, `codigo varchar N`, `comissao_regra jsonb S`, `ativo bool N` | UQ empresa/código e usuário; relações com comandas/pedidos | Desativar; dado trabalhista sensível; retenção legal |
| **SetorProducao** — roteamento KDS | `unidade_id uuid N`, `codigo/nome varchar N`, `ordem int N`, `sla_segundos int S`, `ativo bool N` | UQ unidade/código; IDX ordem; 1:N produção/impressoras | Desativar; auditar configuração |
| **ProducaoItem** — execução por item/setor | `pedido_item_id uuid N`, `setor_id uuid N`, `status enum N`, `prioridade int N`, `quantidade numeric N`, `aceita/iniciada/pronta/retirada_em timestamptz S`, `responsavel_id uuid S`, `tentativa int N` | IDX `(setor_id,status,prioridade,criado_em)`; UQ `(pedido_item_id,setor_id,tentativa)` | Não excluir; sem PII salvo observação referenciada; auditar tempos/transições |
| **ImpressoraSetor** — destino/contingência | `setor_id uuid N`, `nome varchar N`, `driver/endpoint varchar N`, `segredo_ref varchar S`, `ativo bool N`, `ultima_saude timestamptz S` | UQ setor/nome; IDX ativo; N:1 setor | Desativar; credencial só por referência; auditar configuração/reimpressão |
| **Entrega** — execução logística | `pedido_id uuid N`, `endereco_id uuid N`, `entregador_id uuid S`, `status enum N`, `modalidade enum N`, `taxa numeric N`, `previsao/coletada/entregue_em timestamptz S`, `prova_entrega_ref varchar S` | UQ `(empresa_id,pedido_id)`; IDX status/previsão/entregador | Não excluir concluída; localização/PII; retenção mínima operacional |
| **Entregador** — executor próprio/terceiro | `usuario_operacional_id uuid S`, `parceiro varchar S`, `id_externo varchar S`, `nome varchar N`, `telefone_cifrado varchar S`, `status enum N` | UQ usuário ou `(parceiro,id_externo)`; IDX status | Desativar; PII/localização; auditoria e retenção trabalhista/contratual |
| **EnderecoCliente** — endereço versionado | `cliente_id uuid N`, `rotulo varchar S`, `logradouro/numero/bairro/cidade/uf/cep varchar N`, `complemento/referencia varchar S`, `lat/lon decimal S`, `validado_em timestamptz S` | IDX cliente/CEP e geoespacial; sem UQ forçada; 1:N pedidos/entregas por snapshot/ref | PII sensível; soft delete/anônimo se sem obrigação; auditar acesso |
| **Cupom** — regra promocional | `codigo varchar N`, `tipo enum N`, `valor numeric N`, `inicio/fim timestamptz N`, `limite_total/cliente int S`, `regras jsonb N`, `ativo bool N` | UQ `(empresa_id,codigo)`; IDX vigência; 1:N usos | Desativar; auditar regra e aprovação |
| **UsoCupom** — consumo idempotente | `cupom_id/pedido_id uuid N`, `cliente_id uuid S`, `valor_desconto numeric N`, `status enum N`, `idempotency_key varchar N` | UQ idempotency e `(cupom_id,pedido_id)`; IDX cliente | Não excluir, estornar logicamente; PII indireta; retenção com pedido |
| **ConsentimentoMarketing** — prova LGPD | `cliente_id uuid N`, `canal/finalidade enum N`, `status enum N`, `base_legal enum N`, `texto_versao varchar N`, `origem varchar N`, `concedido/revogado_em timestamptz S`, `prova_hash varchar N` | IDX cliente/canal/status; UQ versão/evento; N:1 cliente | Append-only; dado jurídico sensível; reter prova e auditar |
| **ConversaAtendimento** — sessão omnichannel | `cliente_id uuid S`, `canal enum N`, `id_externo varchar S`, `status enum N`, `contexto jsonb S`, `encaminhada_para uuid S`, `iniciada/encerrada_em timestamptz` | UQ canal/id externo; IDX status/cliente; 1:N mensagens, 0:N pedidos | Anonimizar por política; PII; 180 dias padrão; auditar acesso/handoff |
| **MensagemAtendimento** — histórico | `conversa_id uuid N`, `direcao enum N`, `tipo enum N`, `conteudo_cifrado text S`, `arquivo_ref varchar S`, `provedor_id varchar S`, `consentimento_contexto bool N` | UQ provedor/id; IDX conversa/data | Soft delete/anônimo; PII/biometria possível em áudio/imagem; expiração de mídia |
| **ClienteMarketplace** — identidade operacional restrita | `integracao_id uuid N`, `plataforma enum N`, `id_externo_hash varchar N`, `apelido varchar S`, `dados_temporarios jsonb S`, `expira_em timestamptz S`, `convertido_cliente_id uuid S` | UQ integração/id hash; IDX expiração | Sem marketing por padrão; apagar dados temporários; auditar conversão |
| **IntegracaoMarketplace** — configuração adapter | `unidade_id uuid N`, `plataforma enum N`, `conta_externa varchar N`, `segredo_ref varchar N`, `status enum N`, `capacidades jsonb N`, `cursor varchar S` | UQ unidade/plataforma/conta; IDX status | Desativar; segredo fora do DB; auditar credencial/configuração |
| **PedidoExterno** — envelope/reconciliação | `integracao_id uuid N`, `pedido_id uuid S`, `id_externo varchar N`, `versao_externa varchar S`, `status_externo/interno varchar N`, `payload_hash varchar N`, `recebido_em timestamptz N` | UQ `(integracao_id,id_externo)`; IDX pedido/status; 0:1 pedido | Não excluir antes da reconciliação; payload bruto temporário; auditar vínculo |
| **EventoIntegracao** — inbox/outbox externa | `integracao_id uuid N`, `pedido_externo_id uuid S`, `direcao/tipo/status enum N`, `id_externo varchar S`, `idempotency_key varchar N`, `payload_ref varchar S`, `tentativas int N`, `proxima_tentativa timestamptz S`, `erro_codigo varchar S` | UQ integração/idempotency; IDX fila/status/data | Append-only; payload criptografado e TTL; auditar reprocessamento |
| **AuditoriaAcao** — trilha inviolável | `ator_tipo/ator_id varchar N`, `acao/recurso_tipo varchar N`, `recurso_id uuid S`, `antes_hash/depois_hash varchar S`, `motivo varchar S`, `ip_hash/user_agent_hash varchar S`, `correlation_id uuid N`, `ocorrido_em timestamptz N` | IDX recurso, ator, data/correlation; integridade encadeada opcional | Append-only/WORM; acesso restrito; retenção 5 anos configurável |

## 6. Itens, adicionais e observações

Preço, nome, impostos e ficha são snapshots no momento da confirmação. Adicionais têm grupo, cardinalidade e impacto de produção. Observações são tipadas (`cliente`, `alergia`, `cozinha`, `expedicao`, `interna`), com visibilidade por papel; alergia nunca é inferida pela IA. Mudança após envio gera nova versão/evento e, se necessário, nova `ProducaoItem`, impressão de correção e ajuste de estoque.

## 7. Produção e KDS

KDS é padrão: filas por setor, SLA, prioridade justificada, aceite, início, pausa, pronto e retirada. Tela cozinha mostra apenas dados necessários; expedição consolida setores e impede saída incompleta sem override. Alertas são visuais/sonoros configuráveis. Impressão é opcional/contingência: job com chave `(pedido_item,setor,versao,tipo)`, confirmação, número de tentativas e reimpressão auditada. Offline mantém fila local assinada, marca origem offline e reconcilia sem duplicar.

## 8. Salão, mesas e comandas

Mapa por unidade exibe livre/ocupada/reservada/limpeza. Garçom abre comanda, associa mesa/participantes e inclui múltiplos pedidos. Transferência, junção e separação operam por comandos atômicos, preservando histórico; item já produzido não some. Divisão aceita por item, participante, partes iguais ou valor; pagamento misto cria vários `Pagamento`. Fechamento exige saldo zero ou autorização de recebimento posterior. UI responsiva oferece alvos grandes, modo tablet/celular, atualização incremental e aviso de item pronto.

## 9. Garçons e permissões

Garçom vê sua unidade, mesas e comandas atribuídas; cria pedido e solicita alterações. Desconto acima da alçada, cancelamento produzido, transferência entre responsáveis e fechamento posterior exigem gerente. Identidade, empresa e unidade vêm da sessão autenticada.

## 10. Balcão e retirada

Balcão pode ser antecipado ou pagamento na saída. Retirada captura nome/senha, previsão e contato mínimo. A política decide cozinha antes do pagamento; expedição só entrega com pagamento ou override permitido. Tela registra chamada e retirada sem expor telefone completo.

## 11. Delivery próprio

Cardápio publicado deriva de produtos ativos/disponíveis; carrinho valida preço/estoque no fechamento. Cliente escolhe endereço validado, área (polígono/CEP), taxa e prazo versionados. Cupom e cashback são reservas idempotentes. Pagamento segue política; acompanhamento lê projeção de eventos. Cancelamento calcula estágio, estorno e desperdício. Repetir pedido reconstrói carrinho e revalida tudo. Entrega pode ser própria ou adapter terceirizado, sempre sob `Entrega` comum.

## 12. Expedição e entregadores

Expedição confirma todos os setores, embalagem e conferência; atribuição considera disponibilidade sem automatizar decisão crítica. Entregador recebe só endereço/contato necessários, registra coleta, rota, tentativa e prova mínima. Falha retorna à expedição/atendimento; reatribuição e conclusão manual exigem motivo.

## 13. Integrações com marketplaces

Adapters `MarketplaceAdapter` (iFood, 99Food, Keeta e futuros) traduzem capacidades: `receber_pedido`, `aceitar/rejeitar`, `atualizar_status`, `cancelar`, `consultar/reconciliar`. `PedidoExterno` usa `(integracao_id,id_externo)` para idempotência; inbox persiste antes de responder. Eventos fora de ordem são comparados por versão/data e reconciliados. Erros transitórios usam backoff exponencial + jitter e DLQ; permanentes aguardam operador. Limitações (edição, pagamento, dados do cliente, SLA e status aceitos) ficam em `capacidades`, não em condicionais do domínio.

## 14. CRM e conversão para canal próprio

Cliente de marketplace é operacional, mínimo, temporário e **sem autorização de marketing por padrão**. Conversão não copia autorização: exige WhatsApp próprio validado e consentimento/base legal por finalidade, com opt-out simples.

```text
marketplace -> convite por QR/canal permitido -> cadastro voluntário -> aceite comprovado
-> cupom -> primeira compra direta -> relacionamento autorizado -> opt-out respeitado
```

Cupom/cashback não condicionam consentimento indevido. Origem, texto aceito, prova e revogação são registrados.

## 15. Mica I.A.

Preservar interpretação, itens/total, pagamento/troco, multimodal, cadastro de cliente e integração de teste. Evolução:

* **Mica Conversa:** sessão, histórico, intenção, consentimento, moderação e handoff.
* **Mica Carrinho:** resolução estrita contra catálogo, quantidades/adicionais e cálculo determinístico.
* **Mica Pedido:** confirmação explícita de itens/total/endereço; cria pedido pendente e valida estoque.
* **Mica Pagamento:** oferece método e consulta o serviço; nunca declara Pix pago sem evento real.
* **Mica Pós-venda:** acompanhamento, suporte, avaliação e marketing somente autorizado.

Ausência/ambiguidade de correspondência gera pergunta ou humano: nunca inventar fallback nem selecionar o primeiro produto. IA produz proposta estruturada validada por schema; serviços calculam valores e executam comandos idempotentes. Cozinha e entrega recebem eventos do Pedido, não texto do modelo.

## 16. Gerente IA Operacional

Tools futuras tipadas: consultar pedidos/atrasos/mesas/cozinha/entregas/estoque; priorizar pedido; pausar produto; sugerir compra; gerar relatório; preparar campanha; acompanhar conversão. Consultas respeitam tenant e RBAC. Priorizar, pausar, publicar campanha, alterar estoque ou concluir/cancelar exigem permissão, preview, confirmação humana vinculada ao comando, motivo e auditoria; compra é apenas sugestão na V1. O Gerente IA não acessa SQL/segredos diretamente. **PDV e caixa não terão comando de voz automático.**

## 17. Pagamentos

Uma obrigação pode ter múltiplas transações e métodos. Webhook é autenticado, persistido e idempotente; reconciliação confirma o provedor. `pendente` não equivale a pago. Dinheiro/cartão na entrega ficam `aguardando_entrega`; salão, `aguardando_fechamento`. Pagamento misto calcula saldo com `Decimal`. Recebimento posterior requer papel autorizado, identidade, motivo, vencimento e evento.

## 18. Vendas e financeiro

Venda nasce quando o critério financeiro do canal é satisfeito: pagamento confirmado, comanda fechada ou recebimento posterior autorizado. Projeções separam pedidos, faturamento reconhecido, recebível e caixa recebido. Uma venda pode consolidar pedido/comanda conforme regra fiscal; vínculos preservam rastreabilidade. Registros legados continuam nos relatórios com `origem=legado`.

## 19. Estoque, reserva e baixa

Usar ledger de movimentos e uma única política de reconhecimento:

1. Confirmação pode gerar **reserva** por snapshot da ficha, em transação com lock/concorrência otimista.
2. Início/aceite de produção gera **baixa de consumo** e converte/libera a reserva; é o padrão para produzíveis.
3. `Venda` nunca baixa novamente; apenas reconhece financeiro. Produtos não produzíveis podem usar baixa na expedição configurada, jamais simultaneamente.
4. Cancelamento antes da produção libera reserva. Durante/depois, registra consumo e desperdício recuperável/não recuperável.
5. Devolução só repõe item elegível e inspecionado; alimento preparado normalmente vira perda.
6. Insuficiência bloqueia confirmação/liberação ou exige substituição/override autorizado, nunca saldo silenciosamente negativo.
7. Pedidos simultâneos usam update condicional/lock e retry curto.
8. Chave única `(empresa_id,origem_tipo,origem_id,tipo_movimento,insumo_id,versao)` torna cada movimento idempotente.

## 20. Cancelamentos, estornos e devoluções

Cancelamento é saga: autorizar -> cancelar itens ainda possíveis -> parar produção -> liberar/resolver estoque -> cancelar entrega -> estornar pagamento -> ajustar venda por documento compensatório -> notificar. Falha parcial fica visível para reconciliação. Pedido concluído não volta de estado; devolução/estorno cria fluxo relacionado. Motivo e alçada são obrigatórios.

## 21. Segurança e auditoria

RBAC por empresa/unidade; autorização no service; MFA para administrador/financeiro; secrets manager; TLS; criptografia de PII; logs sem tokens/payload integral; rate limit e assinatura de webhook. Auditoria registra ator humano/IA/sistema, tenant obtido da sessão, comando, motivo, antes/depois hash, correlação e confirmação. Exportação, reimpressão, override, desconto, cancelamento e acesso a PII são auditados.

### 21.1 Matriz de permissões

Legenda: `E` executa, `S` solicita, `C` confirma ação crítica, `V` visualiza no escopo, `—` negado.

| Ação | Admin | Gerente | Caixa | Garçom | Cozinha | Expedição | Entregador | Atendimento | Financeiro | Gerente IA |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Configurar empresa/papéis | E/C | S | — | — | — | — | — | — | V | — |
| Criar/alterar pedido não produzido | E | E | E | E | — | — | — | E | V | S |
| Enviar/operar produção | C | E | S | S | E | V | — | V | — | S |
| Priorizar/pausar produto | C | E/C | — | — | S | S | — | V | — | S + confirmação |
| Cancelar antes/depois de produção | C | C | E/S | S | S | S | — | S | V | S + confirmação |
| Abrir/transferir/fechar comanda | C | E/C | E | E/S | — | — | — | S | V | S + confirmação |
| Capturar/confirmar pagamento | V | C | E | S | — | — | S (entrega) | S | E/C | — |
| Estornar/recebimento posterior | C | C | S | — | — | — | — | S | E/C | S + confirmação |
| Operar entrega | V | E | V | V | — | E | E (atribuída) | V/S | — | S |
| Ajustar estoque | C | E/C | — | — | S | S | — | — | V | S + confirmação |
| Campanha/consentimento | C | C | — | — | — | — | — | E/S | V | rascunho + confirmação |
| Relatórios financeiros | V | V | escopo caixa | — | — | — | — | — | E | V agregado |

Ações críticas exigem reautenticação/dupla confirmação conforme valor: estorno, desconto acima da alçada, cancelamento produzido, override de risco/estoque/pagamento, fechamento posterior, reabertura lógica, exportação de PII, configuração e campanha.

## 22. LGPD e consentimento de marketing

Inventário de finalidade e base legal antecede implementação. Operação do pedido não implica marketing. Registrar versão do texto, canal, finalidade, origem, horário e prova; revogação é imediata nos consumidores e preserva apenas evidência necessária. Aplicar direitos do titular com workflow de busca, exportação, correção e anonimização, respeitando retenções legais. Áudio, imagem, endereço, localização e WhatsApp têm acesso e prazo restritos.

## 23. Eventos do sistema

Envelope: `event_id`, `event_type`, `schema_version`, `occurred_at`, `empresa_id`, `unidade_id`, `aggregate_type/id/version`, `correlation_id`, `causation_id`, `actor`, `payload`. PII nunca vai no envelope quando uma referência resolve.

| Evento | Emissor -> consumidores | Payload mínimo / chave de idempotência | Sensibilidade, persistência e retry |
|---|---|---|---|
| `pedido.criado` | Pedido -> projeções/CRM | pedido, canal, totais / `pedido:id:v1` | cliente por ID; outbox; exponencial |
| `pedido.confirmado` | Pedido -> política/estoque | pedido, versão, política / `pedido:id:confirmado:v` | sem PII; permanente; retry |
| `pedido.enviado_producao` | Pedido -> KDS/impressão | pedido, itens/setores / `pedido:id:producao:v` | observação filtrada; permanente; DLQ |
| `producao.iniciada` | Produção -> pedido/estoque/SLA | produção item, setor, hora / `producao:id:iniciada:v` | sem PII; permanente; retry |
| `producao.pronta` | Produção -> expedição/garçom | item, pedido, setor / `producao:id:pronta:v` | sem PII; permanente; retry |
| `pagamento.confirmado` | Pagamento -> venda/pedido | pagamento, valor, método, ref / `transacao:id:confirmada` | financeiro; permanente; reconciliação |
| `comanda.fechada` | Comanda -> venda/mesa | comanda, pedidos, totais / `comanda:id:fechada:v` | financeiro; permanente; retry |
| `entrega.atribuida` | Entrega -> entregador/atendimento | entrega, entregador, previsão / `entrega:id:atribuida:v` | IDs, endereço sob consulta; retry |
| `entrega.concluida` | Entrega -> pedido/pagamento/CRM | entrega, hora, prova ref / `entrega:id:concluida:v` | localização/prova restrita; retry |
| `cliente.consentiu_marketing` | Consentimento -> CRM/campanhas | cliente, canal, finalidade, versão / `consentimento:id` | jurídico; permanente; retry imediato |
| `cliente.cancelou_marketing` | Consentimento -> supressão/campanhas | cliente, canal, finalidade / `revogacao:id` | jurídico; prioridade máxima/DLQ |
| `estoque.reservado` | Estoque -> pedido/projeção | pedido, movimento IDs / `estoque:origem:reserva:v` | sem PII; ledger; retry |
| `estoque.baixado` | Estoque -> custo/projeção | origem, movimentos / `estoque:origem:baixa:v` | custo restrito; ledger; retry |
| `estoque.liberado` | Estoque -> disponibilidade | origem, movimentos / `estoque:origem:libera:v` | sem PII; ledger; retry |
| `venda.criada` | Financeiro -> dashboard/fiscal | venda, pedido, valores / `venda:id:criada` | financeiro; permanente; retry/DLQ |

Consumidores registram `event_id` em inbox. Schema é aditivo e versionado; reprocessamento é seguro.

## 24. Estratégia de migração

Aplicar expand/migrate/contract sem destruição: backup e restore ensaiado; modelos/contratos primeiro; tabelas novas aditivas; `pedido_id` nulo em Venda; escrita sombra e reconciliação; PDV atrás de flag; backfill apenas de vínculo/projeção quando seguro; migração canal a canal; métricas e rollback da flag. Nunca converter Venda legada em pedido fictício automaticamente. Detalhes no [plano de migração](plano-migracao-pedidos-v1.md).

## 25. Estratégia de testes

* Contrato/schema e tabela de decisão da cozinha (incluindo property-based).
* Cada transição: feliz, proibida, autorização, idempotência e concorrência.
* Unitários de valores, estoque, cupom, cashback, risco e adapters.
* Integração com banco efêmero: outbox/inbox, locks, rollback e reconciliação.
* Contract tests por provedor; webhooks assinados, duplicados, atrasados e fora de ordem.
* E2E Playwright por canal e papel; acessibilidade/responsividade.
* Segurança: isolamento multiempresa, IDOR, RBAC, secrets/PII e prompt injection.
* Migração: cópia anonimizada, contagens/somas/checksums, relatórios antes/depois e restore.
* Resiliência/carga: pico simultâneo, KDS offline, impressão, DLQ e observabilidade.

Nenhum teste usa banco/credencial real. Fixtures existentes permanecem até a migração controlada.

## 26. Sequência de implementação por PRs

A ordem revisada antecipa tenant, auditoria, eventos e estoque antes das UIs; separa contratos de ORM e entrega um vertical slice do PDV antes da Central. Ver [plano de PRs](plano-prs-operacao-v1.md). Cada PR pequeno tem flag, testes, telemetria e rollback.

## 27. Critérios de aceite da nova V1

1. Todo canal cria Pedido pelo mesmo serviço e nenhum conclui Venda diretamente.
2. Produção e pagamento evoluem independentemente segundo política versionada.
3. Todos os estados/transições deste projeto têm autorização, evento, auditoria e testes.
4. Repetição de comando/webhook/evento não duplica pedido, baixa, impressão, cashback ou venda.
5. Estoque concorrente nunca fica negativo sem override explícito; Venda não causa segunda baixa.
6. Venda só nasce pelos três critérios financeiros definidos e relatórios conciliam legado/novo.
7. Isolamento multiempresa e matriz RBAC passam testes negativos.
8. Mica nunca inventa/seleciona item incerto nem confirma pagamento; handoff funciona.
9. Marketplace não autoriza marketing; consentimento e opt-out propagam de forma comprovável.
10. KDS funciona por setor e contingência não duplica tickets.
11. Migração e rollback são ensaiados com reconciliação sem perda/destruição.
12. Suítes unitária, integração, contrato, segurança e E2E ficam verdes com SLOs observáveis.

## Matriz de liberação para cozinha

Precedência: pedido válido/confirmado -> risco/estoque/bloqueio -> regra explícita do canal/método -> política versionada -> aprovação. Alto risco sempre exige responsável, mesmo se outra linha permitir.

| Origem | Pagamento/estado | Política/condição | Decisão padrão | Código | Confirmação/responsável |
|---|---|---|---|---|---|
| Delivery próprio | dinheiro na entrega / aguardando_entrega | dentro de área/limite | permitir | `DELIVERY_COD_DINHEIRO` | não |
| Delivery próprio | cartão na entrega / aguardando_entrega | adquirência offline permitida | permitir | `DELIVERY_COD_CARTAO` | não |
| Delivery próprio | Pix online / pendente | antecipado | bloquear | `PIX_AGUARDANDO_CONFIRMACAO` | confirmação do gateway; operador não substitui |
| Delivery próprio | Pix / pago | confirmado/reconciliado | permitir | `PAGAMENTO_CONFIRMADO` | não |
| Retirada | dinheiro no local / não iniciado | `retirada_pos_pago=true` | permitir | `RETIRADA_PAGAMENTO_LOCAL` | política; gerente se acima do limite |
| Retirada | dinheiro no local | política antecipada | bloquear | `RETIRADA_EXIGE_ANTECIPADO` | caixa/gerente após pagamento |
| Retirada | Pix online / pendente | padrão | bloquear | `PIX_AGUARDANDO_CONFIRMACAO` | gateway |
| Mesa | comanda aberta/em consumo | limite disponível | permitir | `COMANDA_ABERTA` | garçom autenticado |
| Balcão | pagamento na saída / aguardando_fechamento | política permite | permitir | `BALCAO_PAGAMENTO_SAIDA` | operador; gerente acima do limite |
| Balcão | antecipado / pendente | política antecipada | bloquear | `BALCAO_EXIGE_PAGAMENTO` | pagamento confirmado |
| Marketplace | pedido confirmado pela plataforma | assinatura/idempotência válidas | permitir | `MARKETPLACE_CONFIRMADO` | não |
| Marketplace | não confirmado/inconsistente | qualquer | bloquear | `EXTERNO_NAO_RECONCILIADO` | atendimento/gerente após reconciliação |
| Qualquer | parcialmente pago | política aceita parcial e saldo coberto | avaliar limite | `PARCIAL_POLITICA` | gerente se saldo > alçada |
| Qualquer | pago | sem outros bloqueios | permitir | `PAGAMENTO_CONFIRMADO` | não |
| Qualquer | alto risco | qualquer | bloquear | `RISCO_ALTO_APROVACAO` | gerente/admin com motivo |
| Qualquer | estoque insuficiente | qualquer | bloquear | `ESTOQUE_INSUFICIENTE` | gerente só com substituição/override auditado |
| Qualquer | total acima do limite do canal/cliente novo | pós-pago | bloquear | `LIMITE_POS_PAGO_EXCEDIDO` | gerente/financeiro conforme alçada |
| Qualquer | cliente bloqueado/fraude | qualquer | bloquear | `CLIENTE_RESTRITO` | gerente/admin; revisão de risco |
| Qualquer | confirmação manual válida | política autoriza override | permitir | `OVERRIDE_AUTORIZADO` | papel exigido + motivo + expiração |

### Contrato futuro

```python
def pode_enviar_para_cozinha(
    pedido: PedidoSnapshot,
    politica: PoliticaCozinha,
    contexto: ContextoDecisao,
) -> DecisaoCozinha:
    """Função pura; não grava, não chama gateway e não consulta contexto global."""

class DecisaoCozinha:
    permitido: bool
    codigo_decisao: str
    justificativa: str
    confirmacao_exigida: bool
    responsavel_necessario: str | None
```

`contexto` contém empresa/unidade autenticadas, risco, estoque, limite, confirmação (ator, papel, motivo, validade), estado reconciliado e horário; `politica` contém ID/versão. A chamada grava entrada resumida, resultado, política e correlation ID em `PedidoEvento`/auditoria. Códigos são estáveis; justificativa é apresentação, não lógica.
