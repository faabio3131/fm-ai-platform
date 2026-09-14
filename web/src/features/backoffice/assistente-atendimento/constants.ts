export const ESTADO_LABELS: Record<string, string> = {
  aguardando_dados_cliente: "Aguardando dados do cliente",
  aguardando_modalidade_entrega: "Aguardando modalidade",
  aguardando_endereco_entrega: "Aguardando endereço",
  aguardando_forma_pagamento: "Aguardando forma de pagamento",
  aguardando_confirmacao_cliente: "Aguardando confirmação",
  checkout_registrado: "Checkout registrado",
  handoff_humano: "Handoff humano",
};

export const ESTADO_COLORS: Record<string, string> = {
  aguardando_dados_cliente: "bg-amber-500/20 text-amber-300",
  aguardando_modalidade_entrega: "bg-amber-500/20 text-amber-300",
  aguardando_endereco_entrega: "bg-amber-500/20 text-amber-300",
  aguardando_forma_pagamento: "bg-amber-500/20 text-amber-300",
  aguardando_confirmacao_cliente: "bg-amber-500/20 text-amber-300",
  checkout_registrado: "bg-green-500/20 text-green-300",
  handoff_humano: "bg-red-500/20 text-red-300",
};

export const MODALIDADE_LABELS: Record<string, string> = {
  retirada: "Retirada",
  entrega: "Entrega",
  indefinida: "Indefinida",
};