# ADR — Evolution como transporte WhatsApp do Kordena V1

## Decisão

O Kordena suporta `meta` e `evolution` como provedores distintos da capacidade
`mensageria.whatsapp`. OpenAI/Gemini continuam sendo provedores cognitivos e não
participam do transporte de mensagens.

Não existe fallback implícito entre Meta e Evolution. O runtime exige exatamente
um provedor WhatsApp habilitado e homologado por tenant/unidade; zero ou dois
provedores falham fechado.

## Responsabilidades

- A FM Tecnologia provisiona a URL e a API key da Evolution, além do token de
  webhook exclusivo, no Control Plane/Vault da unidade.
- O cliente não cria aplicativo na Meta e não recebe a API key da plataforma.
- O cliente apenas gera o QR temporário, lê com o WhatsApp autorizado, verifica
  a conexão e pode desconectar a sessão.
- A instância é determinística e isolada por `tenant_id + unidade_id`.
- O QR permanece somente na sessão da interface e nunca é persistido.

## Fluxo

1. A FM provisiona `mensageria.whatsapp--evolution` para a unidade.
2. O cliente solicita o QR no painel de Integrações.
3. O backend cria/consulta a instância e configura um webhook autenticado.
4. Após a leitura, o backend só considera a sessão conectada quando a Evolution
   retorna estado `open`.
5. Entradas autenticadas passam pela inbox idempotente e pelo runtime canônico do
   Assistente; respostas usam o mesmo provedor selecionado.

## Segurança e falhas

- Instâncias, credenciais e webhooks são escopados por tenant/unidade.
- O browser nunca chama a Evolution diretamente.
- Grupos, broadcasts, mensagens próprias e instâncias divergentes são ignorados
  ou rejeitados.
- Um envio mutável não é repetido após resultado incerto.
- Falha do WhatsApp não reverte Pedido, Pagamento, Estoque, KDS ou Entrega.

## Homologação externa pendente

A construção interna não prova o provedor real. A homologação posterior deve
validar a versão instalada da Evolution na Contabo, QR real, callback autenticado,
entrada/saída reais, reconexão após reinício e isolamento entre duas unidades.
