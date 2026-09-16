export const INTEGRACAO_LABELS: Record<string, string> = {
  'social.facebook--meta': 'Meta · Facebook',
  'social.instagram--meta': 'Meta · Instagram Business',
  'mensageria.whatsapp--meta': 'Meta · WhatsApp Business',
  'mapas--google_maps': 'Google Maps',
  'pagamentos.pix--pagbank': 'PagBank · PIX',
  'pagamentos.pix--mercado_pago': 'Mercado Pago · PIX',
  'ia.generativa--gemini': 'Google Gemini',
};

export const PARAMETRO_LABELS: Record<string, string> = {
  page_id: 'Facebook Page ID',
  facebook_page_id: 'Facebook Page ID',
  business_account_id: 'Business Account ID',
  app_id: 'App ID',
  phone_number_id: 'WhatsApp Phone Number ID',
  origin_address: 'Endereço de origem',
  country_code: 'País (ex.: BR)',
  language: 'Idioma (ex.: pt-BR)',
  currency: 'Moeda (ex.: BRL)',
  notification_url: 'URL de notificação / webhook',
  model: 'Modelo',
};

export const CREDENCIAL_LABELS: Record<string, string> = {
  access_token: 'Access Token',
  app_secret: 'App Secret',
  webhook_verify_token: 'Webhook Verify Token',
  browser_api_key: 'Browser API Key',
  server_api_key: 'Server API Key',
  api_token: 'API Token',
  webhook_secret: 'Webhook Secret',
  api_key: 'API Key',
};

export const AMBIENTE_LABELS: Record<string, string> = {
  sandbox: 'Sandbox',
  homologacao: 'Homologação',
  producao: 'Produção',
};

export const PRONTIDAO_LABELS: Record<string, string> = {
  desativado: 'Desativado',
  bloqueado: 'Bloqueado',
  configurado: 'Configurado',
  pronto: 'Pronto',
};

export const PRONTIDAO_COLORS: Record<string, string> = {
  desativado: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
  bloqueado: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  configurado: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
  pronto: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
};

export function getLabel(key: string, fallback?: string): string {
  return INTEGRACAO_LABELS[key] || PARAMETRO_LABELS[key] || CREDENCIAL_LABELS[key] || fallback || key;
}