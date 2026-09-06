# Kordena Enterprise Web

Frontend enterprise desacoplado da V1, baseado em Next.js App Router, TypeScript, Tailwind CSS v4 e componentes shadcn/ui.

## Desenvolvimento local

1. Backend com CORS de desenvolvimento:

   ```bash
   uvicorn 'http_api.frontend_app:build_frontend_http_app' --factory --host 0.0.0.0 --port 8000
   ```

2. Frontend:

   ```bash
   cd web
   npm install
   npm run dev
   ```

3. Acesse `http://localhost:3000`.

`NEXT_PUBLIC_API_URL` usa `http://localhost:8000` por padrão e pode ser sobrescrito via `.env.local`.

## Health contract

O novo cliente tenta `/health/live` primeiro. A V1 congelada em `v1.0.0-rc1` expõe `/healthz`; por isso existe fallback exclusivo para HTTP 404, sem alteração da rota backend nesta fase.

## Contexto HTTP

`src/lib/api.ts` oferece um wrapper que injeta, quando informados, `Authorization: Bearer`, `X-Tenant-ID` e `X-Unit-ID`. Ações idempotentes podem adicionar `Idempotency-Key` via `RequestInit.headers`.
