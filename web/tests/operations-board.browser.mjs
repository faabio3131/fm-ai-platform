import { chromium } from "playwright";
import assert from "node:assert/strict";

const base = "http://127.0.0.1:3000";
const order = (id, status) => ({pedido_id:id,canal:"delivery",status,criado_em:new Date().toISOString(),atualizado_em:new Date().toISOString(),total:"42.00",quantidade_itens:2,cliente_id:null,financeiro:{situacao:"pendente",valor_previsto:"42.00",valor_pago:"0",pagamento_ids:[],venda_financeira_id:null,venda_legada_id:null,reconciliacao_id:null,reconciliacao_status:null},possui_alerta:false,origem:"teste",versao:1});
const records = [order("novo0001","rascunho"),order("prep0001","em_preparo"),order("pront001","pronto")];
const operator = (permissions) => ({usuario_id:"user-test",nome:"Operador de teste",email:"teste@example.invalid",tenant_id:"tenant-test",unidade_ativa_id:"unit-test",papeis:["gerente"],permissoes:permissions});
const browser = await chromium.launch({headless:true});
let failures=0;
async function scenario(name, permissions, execute) {
  const context = await browser.newContext({viewport:{width:1365,height:900}});
  const page = await context.newPage();
  let calls=0;
  await page.route("**/v1/auth/me", route => route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(operator(permissions))}));
  await page.route("**/v1/auth/unidades", route => route.fulfill({status:200,contentType:"application/json",body:JSON.stringify([{id:"unit-test",nome:"Unidade de teste"}])}));
  // The premium staging application has an independent commercial entitlement
  // gate; mock its authorized response without disabling the production guard.
  await page.route("**/v1/commercial/access", route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      tenant_id: "tenant-test",
      enforcement_enabled: true,
      managed: true,
      product_account_id: "account-test",
      operational_allowed: true,
      entitled: true,
      access_mode: "full",
      reason: "subscription_active",
      revision: 1,
      stale: false,
    }),
  }));
  await page.route("**/v1/pedidos?*", route => {calls++;return route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({itens:records,pagina:1,tamanho_pagina:100,total:records.length})});});
  try {await page.goto(base+"/central-operacoes",{waitUntil:"domcontentloaded"});await execute(page,()=>calls);console.log("PASS",name);}
  catch(e){failures++;console.error("FAIL",name,e);}
  finally {await context.close();}
}
try {
 await scenario("authorized user sees orders in three columns and manual refresh",["pedido.visualizar"],async(page,calls)=>{
   await page.getByRole("heading",{name:"Central de Operações"}).waitFor();
   for(const label of ["Novos","Em preparo","Prontos"]) assert.equal(await page.getByRole("heading",{name:label,exact:true}).count(),1);
   for(const id of ["novo0001","prep0001","pront001"]) await page.getByText("Pedido #"+id).waitFor();
   assert.equal(calls(),1);
   await page.getByRole("button",{name:"Atualizar"}).click();
   await page.waitForFunction(()=>document.body.textContent?.includes("Última atualização:"));
   assert.ok(calls()>=2);
   await page.screenshot({path:"operations-board-desktop.png",fullPage:true});
 });
 await scenario("unauthorized user sees no order data",[],async(page,calls)=>{
   await page.getByText("Você não tem permissão para visualizar pedidos.").waitFor();
   assert.equal(calls(),0);
   assert.equal(await page.getByText("Pedido #novo0001").count(),0);
 });
 await scenario("API failure shows an alert and preserves previous data",["pedido.visualizar"],async(page)=>{
   await page.getByText("Pedido #novo0001").waitFor();
   await page.route("**/v1/pedidos?*",route=>route.fulfill({status:503,contentType:"application/json",body:JSON.stringify({erro:"indisponivel"})}));
   await page.getByRole("button",{name:"Atualizar"}).click();
   await page.getByRole("alert").getByText(/Não foi possível atualizar os pedidos/).waitFor();
   assert.equal(await page.getByText("Pedido #novo0001").count(),1);
 });
 await scenario("automatic refresh polls again after 15 seconds",["pedido.visualizar"],async(page,calls)=>{
   await page.getByText("Pedido #novo0001").waitFor();
   const initial = calls();
   await page.waitForFunction(() => document.body.textContent?.includes("Última atualização:"));
   await page.waitForTimeout(16000);
   assert.ok(calls()>initial,`Expected polling after 15s; got ${calls()} requests`);
 });
 await scenario("mobile layout renders",["pedido.visualizar"],async(page)=>{
   await page.setViewportSize({width:390,height:844});
   await page.getByText("Pedido #novo0001").waitFor();
   await page.screenshot({path:"operations-board-mobile.png",fullPage:true});
 });
} finally {await browser.close();}
if(failures) process.exitCode=1;
