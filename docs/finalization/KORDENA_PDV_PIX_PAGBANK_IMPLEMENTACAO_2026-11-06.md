# Fechamento interno Kordena V1 — Pix PagBank no PDV Web

## Autoridade e segurança
O checkout `/v1/pdv/checkout` cria a obrigação canônica e a reserva de estoque.
`POST /v1/pdv/pagamentos/{id}/iniciar-pix-pagbank` gera QR/copia-e-cola no PagBank
por um adapter com credencial resolvida do tenant/unidade; a Application executa
a escrita de vínculo `ORDE_` e trilha de auditoria numa UoW.
`POST /v1/pdv/pagamentos/{id}/verificar-pix-pagbank` reconcilia apenas a ordem
já vinculada pela própria aplicação, sem aceitar estado do navegador.
A autorização exige `pdv.operar` + `pagamento.registrar`, e a reconciliação
também exige `pagamento.confirmar`. Nenhum CPF/CNPJ é persistido pela nova rota;
seu uso se limita à requisição ao provedor via HTTPS. Não gravar payload
de pagamento, chave Pix, documento ou token em logs.

## Configuração externa a realizar no estabelecimento
* Credencial ativa PagBank por unidade, registrada pelo mecanismo de referência
  do banco; token verdadeiro permanece no `SecretStore`, nunca no Git.
* `FM_AI_PAGBANK_ENV=sandbox` em homologação ou `production` somente após
  evidência de conformidade da conta/contrato específico.
* `FM_AI_PAGBANK_NOTIFICATION_URL=https://api.kordenaia.com.br/webhooks/pagbank`
  e assinatura de webhook validada antes de qualquer mutação financeira.
* Cliente informa nome, e-mail e CPF/CNPJ exigidos pelo PagBank; a criação do
  QR exige todos os campos. A configuração/QR reais requerem teste no PSP.
* Em caso de timeout entre provider e persistência, o mesmo ID e chave
  idempotente devem ser reutilizados. Nunca confirmar Pix manualmente.

## Gates internos obrigatórios
- API/PDV com Caixa autenticado: checkout pendente, criação de cobrança, QR,
  consulta pendente, reenvio idempotente, prova de tenant/unidade.
- Falta de credencial: 503, sem converter para pago.
- Confirmado pelo provedor: finalizador canônico de pedido/estoque via
  `application.pagbank_reconciliacao` existente, com webhook assinado e replay.
- Frontend Next.js: build, lint, testes funcionais e regressão integral.
- Sem deploy até liberação separada do proprietário: `production` gera deploy
  Contabo automático.

## Não confundir com construção completa dos demais meios
Cartão de débito/crédito requer adapter de adquirência homologável,
capture/authorization, webhook e estorno próprios; apenas registrar método
no checkout não é cobrança. O Mercado Pago Pix também possui adapters anteriores,
mas seu cutover Web só pode ser declarado pronto após contrato equivalente.
