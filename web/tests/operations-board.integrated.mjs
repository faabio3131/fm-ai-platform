import { chromium } from "playwright";
import assert from "node:assert/strict";

const web = "http://127.0.0.1:3000";
const api = "http://127.0.0.1:8000";
const browser = await chromium.launch({headless:true});
const context = await browser.newContext({viewport:{width:1365,height:900}});
const page = await context.newPage();
let orderRequests = 0;
page.on("request", request => {
  if (request.url().startsWith(api + "/v1/pedidos?")) orderRequests++;
});
try {
  const initial = await context.request.get(api + "/v1/pedidos?pagina=1&tamanho_pagina=100");
  assert.ok([401,403].includes(initial.status()), "API must reject unauthenticated requests");

  await page.goto(web + "/login?next=%2Fcentral-operacoes");
  await page.getByLabel("E-mail").fill("gerente-orders-center@example.com");
  await page.locator("#senha").fill("Senha-Segura-Orders-Center-123");
  await page.getByRole("button",{name:"Entrar",exact:true}).click();
  await page.getByRole("heading",{name:"Central de Operações"}).waitFor({timeout:20000});
  const firstCard = page.locator('a[href="/pedidos"]').filter({hasText:"Pedido #"}).first();
  await firstCard.waitFor();
  assert.match(await firstCard.innerText(), /Pedido #/);
  assert.ok(orderRequests >= 1, "board must call real FastAPI");
  const me = await page.evaluate(async base => {
    const response = await fetch(base + "/v1/auth/me",{credentials:"include"});
    return {status:response.status,data:await response.json()};
  },api);
  assert.equal(me.status,200);
  assert.equal(me.data.unidade_ativa_id,"unidade-orders-center-http");
  await page.screenshot({path:"operations-board-integrated-desktop.png",fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await firstCard.waitFor();
  await page.screenshot({path:"operations-board-integrated-mobile.png",fullPage:true});
  console.log("PASS: real login + signed cookie + real FastAPI order list + tenant/unit scope + desktop/mobile screenshots");
} finally {
  await browser.close();
}
