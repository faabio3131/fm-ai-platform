import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const layout = readFileSync(new URL("../src/app/layout.tsx", import.meta.url), "utf8");
const guard = readFileSync(
  new URL("../src/features/commercial/components/CommercialAccessGuard.tsx", import.meta.url),
  "utf8",
);
const api = readFileSync(
  new URL("../src/features/commercial/services/commercial-access-api.ts", import.meta.url),
  "utf8",
);

test("KCA-11 installs commercial access guard inside authenticated layout", () => {
  assert.match(layout, /CommercialAccessGuard/);
  assert.match(layout, /AuthSessionGuard>[\s\S]*CommercialAccessGuard/);
});

test("KCA-11 paywall is backend-authoritative and preserves logout", () => {
  assert.match(api, /\/v1\/commercial\/access/);
  assert.match(api, /credentials:\s*"include"/);
  assert.match(guard, /operational_allowed/);
  assert.match(guard, /endAuthSession/);
  assert.match(guard, /Seus dados permanecem preservados/);
});
