"""Aplica uma vez o cutover F13-C sobre o app.py preservando o restante do blob."""

from pathlib import Path

APP = Path("app.py")
source = APP.read_text(encoding="utf-8")

IMPORT_ANCHOR = "from application.legacy_bootstrap_transacoes import AplicacaoLegacyBootstrapV1\n"
IMPORTS = """from application.legacy_bootstrap_transacoes import AplicacaoLegacyBootstrapV1
from application.crm_cashback_comercial import (
    consultar_saldo_cashback_legado,
    creditar_cashback_manual,
)
from application.crm_marketing_comercial import despachar_resgate_whatsapp_legado
"""
if source.count(IMPORT_ANCHOR) != 1:
    raise SystemExit("F13C: import anchor divergente")
source = source.replace(IMPORT_ANCHOR, IMPORTS, 1)

HELPER_ANCHOR = "\n# --- 6. BARRA LATERAL (SIDEBAR CORPORATIVA) ---\n"
HELPERS = r'''

def _saldo_cashback_canonico_ui(legacy_cliente_id: int) -> tuple[float, str | None]:
    try:
        resultado = consultar_saldo_cashback_legado(
            session_factory=SessionLocal,
            tenant_id=CURRENT_IDENTITY.tenant_id,
            unidade_id=CURRENT_IDENTITY.unidade_id,
            legacy_cliente_id=int(legacy_cliente_id),
        )
        return float(resultado.saldo), None
    except Exception as exc:
        # Fail-closed: a UI jamais usa saldo legado como fallback.
        return 0.0, str(exc)


def _texto_saldo_cashback_canonico_ui(legacy_cliente_id: int) -> str:
    saldo, erro = _saldo_cashback_canonico_ui(legacy_cliente_id)
    if erro:
        return "Regularização CRM necessária"
    return formatar_moeda_br(saldo)
'''
if source.count(HELPER_ANCHOR) != 1:
    raise SystemExit("F13C: helper anchor divergente")
source = source.replace(HELPER_ANCHOR, HELPERS + HELPER_ANCHOR, 1)

CRM_START = "# ABA 2: CRM E WHATSAPP\n"
PDV_START = "# ABA 3: FRENTE DE CAIXA\n"
start = source.find(CRM_START)
end = source.find(PDV_START)
if start < 0 or end <= start:
    raise SystemExit("F13C: marcadores CRM/PDV divergentes")

crm_block = r'''# ABA 2: CRM E WHATSAPP
# ==============================================================================
with aba2:
    st.header("📢 CRM, Campanhas de Resgate ('Oi, Sumido') & Fidelidade Cashback")
    st.write(
        "Engaje clientes inativos com campanhas consentidas e administre o cashback pela autoridade canônica CRM."
    )

    sub_crm1, sub_crm2 = st.tabs(
        [
            "🔄 Recuperação de Clientes Inativos (Upsell)",
            "💳 Gestão de Fidelidade & Cashback",
        ]
    )

    db_crm_base = get_db()

    with sub_crm1:
        st.subheader("🤖 Automação de Resgate com Inteligência Artificial")
        st.caption(
            "Disparos exigem vínculo CRM, consentimento WhatsApp/promocoes vigente e integração Meta homologada."
        )

        data_corte_inativos = datetime.now() - timedelta(days=15)
        clientes_inativos = (
            db_crm_base.query(Cliente)
            .filter(
                (Cliente.ultima_compra <= data_corte_inativos)
                | (Cliente.status == "Inativo")
            )
            .all()
        )

        st.markdown(
            f"### 👥 Clientes em risco de churn identificados: **{len(clientes_inativos)}**"
        )

        if clientes_inativos:
            for cli in clientes_inativos:
                saldo_cli, erro_saldo_cli = _saldo_cashback_canonico_ui(int(cli.id))
                with st.container():
                    c_col1, c_col2, c_col3 = st.columns([2, 2, 3])
                    with c_col1:
                        st.markdown(f"**👤 {cli.nome}**")
                        st.write(f"📱 WhatsApp: `{cli.whatsapp}`")
                        st.write(f"📌 Status: **{cli.status}**")

                    with c_col2:
                        st.write(
                            f"🕒 Última compra: **{cli.ultima_compra.strftime('%d/%m/%Y')}**"
                        )
                        st.write(f"💰 Total acumulado: **R$ {cli.total_gasto:.2f}**")
                        if erro_saldo_cli:
                            st.caption("💳 Cashback: regularização CRM necessária")
                        else:
                            st.write(
                                f"💳 Cashback disponível: **{formatar_moeda_br(saldo_cli)}**"
                            )

                    msg_resgate_padrao = (
                        f"Olá {cli.nome}! Sentimos sua falta. Preparamos um cupom "
                        "exclusivo de 15% de desconto para você voltar hoje!"
                    )
                    if GENAI_DISPONIVEL:
                        try:
                            prompt_resg = (
                                "Escreva uma mensagem curta, carinhosa e persuasiva de "
                                f"WhatsApp para resgatar o cliente '{cli.nome}'. Ofereça "
                                "15% de desconto com o cupom VOLTA15. Sem clichês em excesso."
                            )
                            resp_resg = generate_content(contents=prompt_resg)
                            if resp_resg and resp_resg.text:
                                msg_resgate_padrao = resp_resg.text.strip()
                        except Exception:
                            pass

                    with c_col3:
                        st.markdown("🤖 **Sugestão de Abordagem I.A.:**")
                        st.info(f'"{msg_resgate_padrao}"')
                        if st.button(
                            f"🚀 Disparar Campanha WhatsApp para {cli.nome}",
                            key=f"btn_zap_resgate_{cli.id}",
                            type="primary",
                        ):
                            try:
                                chave_envio = (
                                    f"crm-resgate-{cli.id}-{date.today().isoformat()}"
                                )
                                resultado_envio = despachar_resgate_whatsapp_legado(
                                    session_factory=SessionLocal,
                                    contexto=CURRENT_IDENTITY.contexto(
                                        origem="app.crm.resgate"
                                    ),
                                    legacy_cliente_id=int(cli.id),
                                    campanha_ref=f"resgate-{date.today().isoformat()}",
                                    texto=msg_resgate_padrao,
                                    idempotency_key=chave_envio,
                                )
                                if resultado_envio.enviado:
                                    st.success(
                                        f"✅ Campanha consentida enviada com sucesso para {cli.nome}."
                                    )
                                else:
                                    st.warning(
                                        "Campanha bloqueada: não existe consentimento "
                                        "WhatsApp/promocoes vigente para este cliente."
                                    )
                            except Exception:
                                st.error(
                                    "Não foi possível enviar a campanha. Verifique o vínculo CRM, "
                                    "o consentimento e a integração Meta/WhatsApp homologada."
                                )
        else:
            st.success(
                "🎉 Nenhum cliente inativo há mais de 15 dias foi identificado no momento."
            )

    with sub_crm2:
        st.subheader("💳 Relatório Geral de Saldos de Cashback")
        st.caption("O saldo exibido é derivado exclusivamente do ledger canônico CRM.")

        todos_clientes = db_crm_base.query(Cliente).all()
        if todos_clientes:
            dados_cb = []
            for cl in todos_clientes:
                dados_cb.append(
                    {
                        "ID": cl.id,
                        "Nome do Cliente": cl.nome,
                        "WhatsApp": cl.whatsapp,
                        "Total Gasto na Loja": f"R$ {cl.total_gasto:.2f}",
                        "Saldo Cashback": _texto_saldo_cashback_canonico_ui(int(cl.id)),
                        "Status": cl.status,
                    }
                )
            st.dataframe(
                pd.DataFrame(dados_cb), use_container_width=True, hide_index=True
            )
        else:
            st.info("Nenhum cliente cadastrado no banco de dados até o momento.")

        if is_test_mode():
            st.markdown("---")
            with st.form("form_e2e_cliente_teste", clear_on_submit=True):
                st.markdown("### 🧪 Cadastro seguro de cliente para testes E2E")
                nome_cliente_e2e = st.text_input("Nome do Cliente E2E")
                whatsapp_cliente_e2e = st.text_input("WhatsApp do Cliente E2E")
                email_cliente_e2e = st.text_input("E-mail do Cliente E2E (opcional)")
                documento_cliente_e2e = st.text_input("CPF/CNPJ do Cliente E2E (opcional)")
                if st.form_submit_button("💾 Salvar Cliente E2E", type="secondary"):
                    documento_normalizado = "".join(
                        caractere for caractere in documento_cliente_e2e if caractere.isdigit()
                    )
                    documento_valido = not documento_normalizado or len(documento_normalizado) in {11, 14}
                    email_normalizado = email_cliente_e2e.strip()
                    if not nome_cliente_e2e.strip() or not whatsapp_cliente_e2e.strip():
                        st.error("Nome e WhatsApp do cliente E2E são obrigatórios.")
                    elif not documento_valido:
                        st.error("CPF/CNPJ deve conter 11 ou 14 dígitos quando informado.")
                    elif email_normalizado and (
                        "@" not in email_normalizado
                        or "." not in email_normalizado.rsplit("@", 1)[-1]
                    ):
                        st.error("Informe um e-mail válido quando preencher o campo.")
                    else:
                        try:
                            criado = AplicacaoLegacyClienteE2EV1(SessionLocal, Cliente).cadastrar(
                                nome=nome_cliente_e2e,
                                whatsapp=whatsapp_cliente_e2e,
                                email=email_normalizado or None,
                                documento_fiscal=documento_normalizado or None,
                            )
                            if not criado:
                                st.error("Cliente E2E já cadastrado com este WhatsApp.")
                            else:
                                st.success("Cliente E2E salvo com sucesso.")
                                st.rerun()
                        except Exception as exc:
                            st.error(f"Erro ao salvar cliente E2E: {exc}")

        st.markdown("---")
        with st.form("form_ajustar_cashback"):
            st.markdown("### ➕ Creditar Saldo de Cashback Manualmente")
            st.caption("O crédito é gravado no ledger e a coluna legada recebe somente a projeção final.")
            col_cb1, col_cb2 = st.columns(2)
            with col_cb1:
                cli_escolhido = st.selectbox(
                    "Selecione o Cliente para o Crédito",
                    todos_clientes,
                    format_func=lambda x: (
                        f"{x.nome} (Saldo Atual: {_texto_saldo_cashback_canonico_ui(int(x.id))})"
                    ),
                )
            with col_cb2:
                valor_add_cb = st.number_input(
                    "Valor do Crédito a Adicionar (R$)",
                    min_value=0.0,
                    value=10.0,
                    step=5.0,
                    format="%.2f",
                )

            if st.form_submit_button("💰 Confirmar Crédito de Cashback", type="primary") and cli_escolhido:
                try:
                    from decimal import Decimal

                    resultado_credito = creditar_cashback_manual(
                        session_factory=SessionLocal,
                        tenant_id=CURRENT_IDENTITY.tenant_id,
                        unidade_id=CURRENT_IDENTITY.unidade_id,
                        legacy_cliente_id=int(cli_escolhido.id),
                        valor=Decimal(str(valor_add_cb)),
                        referencia=f"crm-ui://bonus/{CURRENT_IDENTITY.usuario_id}",
                        idempotency_key=f"crm-bonus-{cli_escolhido.id}-{uuid4()}",
                    )
                    st.success(
                        f"✅ Crédito de {formatar_moeda_br(valor_add_cb)} registrado no ledger. "
                        f"Novo saldo: {formatar_moeda_br(float(resultado_credito.saldo))}."
                    )
                    st.rerun()
                except Exception:
                    st.error(
                        "Não foi possível creditar cashback. O cliente precisa estar vinculado "
                        "ao CRM e qualquer saldo legado anterior deve estar regularizado."
                    )

    db_crm_base.close()

# ==============================================================================
# ABA 3: FRENTE DE CAIXA
'''
source = source[:start] + crm_block + source[end + len(PDV_START):]

old_cashback_ui = '''        if cliente_pdv and cliente_pdv.saldo_cashback > 0:
            usa_cashback_pdv = st.checkbox(
                f"💳 Utilizar Saldo de Cashback deste cliente (Disponível: {formatar_moeda_br(cliente_pdv.saldo_cashback)})",
                key="pdv_usa_cashback",
            )
            if usa_cashback_pdv:
                desconto_cb_pdv = min(total_bruto_pdv, cliente_pdv.saldo_cashback)
'''
new_cashback_ui = '''        saldo_cashback_pdv = 0.0
        erro_cashback_pdv = None
        if cliente_pdv:
            saldo_cashback_pdv, erro_cashback_pdv = _saldo_cashback_canonico_ui(
                int(cliente_pdv.id)
            )
            if erro_cashback_pdv:
                st.caption(
                    "💳 Cashback indisponível até concluir o vínculo/regularização CRM deste cliente."
                )

        if cliente_pdv and saldo_cashback_pdv > 0:
            usa_cashback_pdv = st.checkbox(
                f"💳 Utilizar Saldo de Cashback deste cliente (Disponível: {formatar_moeda_br(saldo_cashback_pdv)})",
                key="pdv_usa_cashback",
            )
            if usa_cashback_pdv:
                desconto_cb_pdv = min(total_bruto_pdv, saldo_cashback_pdv)
'''
if source.count(old_cashback_ui) != 1:
    raise SystemExit("F13C: bloco cashback PDV UI divergente")
source = source.replace(old_cashback_ui, new_cashback_ui, 1)

old_validation = '''                if (
                    cliente_db
                    and usa_cashback_pdv
                    and float(validacao_banco.desconto_cashback)
                    > float(cliente_db.saldo_cashback or 0.0)
                ):
                    st.session_state["pdv_processando"] = False
                    st.error(
                        "Cashback não pode ser maior que o saldo disponível do cliente."
                    )
                    st.stop()
'''
new_validation = '''                if cliente_db and usa_cashback_pdv:
                    saldo_cashback_banco, erro_cashback_banco = _saldo_cashback_canonico_ui(
                        int(cliente_db.id)
                    )
                    if erro_cashback_banco:
                        st.session_state["pdv_processando"] = False
                        st.error(
                            "Cashback indisponível: conclua o vínculo/regularização CRM do cliente."
                        )
                        st.stop()
                    if float(validacao_banco.desconto_cashback) > saldo_cashback_banco:
                        st.session_state["pdv_processando"] = False
                        st.error(
                            "Cashback não pode ser maior que o saldo canônico disponível do cliente."
                        )
                        st.stop()
'''
if source.count(old_validation) != 1:
    raise SystemExit("F13C: validação cashback PDV divergente")
source = source.replace(old_validation, new_validation, 1)

crm_after = source[source.find(CRM_START):source.find(PDV_START)]
pdv_end_marker = "# ABA 4: ESTOQUE, ALMOXARIFADO & VALIDADES COM I.A."
pdv_after = source[source.find(PDV_START):source.find(pdv_end_marker)]
if ".saldo_cashback" in crm_after or ".saldo_cashback" in pdv_after:
    raise SystemExit("F13C: leitura/escrita legada de cashback ainda presente em CRM/PDV")
if "mock_whatsapp_send" in crm_after:
    raise SystemExit("F13C: fake WhatsApp ainda presente no caminho CRM")
for required in (
    "consultar_saldo_cashback_legado",
    "creditar_cashback_manual",
    "despachar_resgate_whatsapp_legado",
):
    if required not in source:
        raise SystemExit(f"F13C: boundary ausente: {required}")

APP.write_text(source, encoding="utf-8")
