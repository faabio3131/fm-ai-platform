import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const board = read("../src/features/orders/components/OperationsBoardWorkspace.tsx");
const route = read("../src/app/central-operacoes/page.tsx");
const registry = read("../src/features/shell/module-registry.ts");
const api = read("../src/features/orders/services/orders-api.ts");

test("new operations route renders the isolated board", () => {
  assert.match(route, /OperationsBoardWorkspace/);
  assert.match(route, /export default function OperationsBoardPage/);
});
test("navigation requires order read permission", () => {
  assert.match(registry, /id: "central-operacoes"[\s\S]*?href: "\/central-operacoes"[\s\S]*?allPermissions: \["pedido\.visualizar"\]/);
});
test("board enforces permission and authenticated unit scope", () => {
  assert.match(board, /auth\.permissions\.includes\("pedido\.visualizar"\)/);
  assert.match(board, /auth\.status !== "authenticated" \|\| !auth\.unitId/);
  assert.match(board, /if \(!allowed\)/);
});
test("board is read-only and uses authenticated GET order listing", () => {
  assert.match(board, /listOrders\(\{ pagina: 1, tamanhoPagina: PAGE_SIZE \}\)/);
  assert.doesNotMatch(board, /sendOrderToConfirmation|cancelOrder|method:\s*["'](?:POST|PUT|PATCH|DELETE)/);
  assert.match(api, /\/v1\/pedidos\?/);
  assert.match(api, /method: "GET"[\s\S]*?credentials: "include"/);
});
test("order-level readiness is not represented as KDS item readiness", () => {
  assert.match(board, /statuses: \["pronto"\]/);
  assert.match(board, /status comercial do pedido/);
});
test("partial pagination and errors are disclosed", () => {
  assert.match(board, /first\.total > first\.itens\.length/);
  assert.match(board, /Exibindo somente os/);
  assert.match(board, /role="alert"/);
});
test("polling stops when hidden and timers are cleaned up", () => {
  assert.match(board, /document\.visibilityState === "visible"/);
  assert.match(board, /clearTimeout\(initial\)/);
  assert.match(board, /clearInterval\(interval\)/);
});
test("existing central orders and KDS routes remain distinct", () => {
  assert.match(registry, /href: "\/pedidos"/);
  assert.match(registry, /href: "\/kds"/);
  assert.match(board, /href="\/pedidos"/);
});
