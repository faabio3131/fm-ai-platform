"""UI comercial do Painel Proprietário / Administrador V1."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from typing import Any, cast

import pandas as pd  # type: ignore[import-untyped]
import streamlit as st
from sqlalchemy.orm import Session
from streamlit.errors import StreamlitPageNotFoundError

from application.administracao_proprietario import AplicacaoAdministracaoProprietarioV1
from core.administracao import (
    ConfiguracaoEstabelecimento,
    EmpresaAdministrativa,
    UnidadeAdministrativa,
)
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.permissoes import MATRIZ_PADRAO, Papel, Permissao
from infra.streamlit_app.auth_ui import verify_sensitive_pin
from infra.streamlit_app.integracoes_admin import render_integracoes_admin

_FORMAS_PAGAMENTO = (
    "dinheiro",
    "pix",
    "cartao_credito",
    "cartao_debito",
    "pagamento_na_entrega",
)


def _contexto(identidade: IdentidadeUsuario):
    return identidade.contexto(origem="streamlit.administracao_proprietario")


def _pin_ok(
    *,
    identidade: IdentidadeUsuario,
    pin: str,
    session_factory: Callable[[], Session],
    permissao: Permissao,
) -> bool:
    return verify_sensitive_pin(
        identity=identidade,
        pin=pin,
        session_factory=session_factory,
        required_permission=permissao,
    )


def _erro_generico(codigo: str) -> None:
    st.error(
        "A operação administrativa não foi concluída. "
        f"Recarregue os dados e tente novamente. Referência: {codigo}."
    )


def _dinheiro(valor: Decimal | None) -> str:
    if valor is None:
        return "Não disponível"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _registrar_acesso_uma_vez(
    app: AplicacaoAdministracaoProprietarioV1,
    *,
    identidade: IdentidadeUsuario,
) -> None:
    key = f"f5_admin_access_audit:{identidade.usuario_id}:{identidade.unidade_id}"
    if st.session_state.get(key):
        return
    try:
        app.registrar_acesso(contexto=_contexto(identidade))
    except Exception:  # noqa: BLE001 - acesso já foi autorizado pelo guard da página
        return
    st.session_state[key] = True


def _render_dashboard(
    app: AplicacaoAdministracaoProprietarioV1,
    *,
    identidade: IdentidadeUsuario,
) -> None:
    contexto = _contexto(identidade)
    try:
        unidades = app.listar_unidades(contexto=contexto)
    except Exception:  # noqa: BLE001
        _erro_generico("F5-DASH-UNIDADES")
        return

    if not unidades:
        st.info("Nenhuma unidade administrativa cadastrada para esta empresa.")
        return

    labels = {u.unidade_id: f"{u.nome_fantasia} · {u.unidade_id}" for u in unidades}
    escolha = st.multiselect(
        "Escopo do dashboard",
        options=[u.unidade_id for u in unidades],
        default=[u.unidade_id for u in unidades if u.ativa],
        format_func=lambda item: labels[item],
        help="Selecione uma ou várias unidades. Vazio não é aceito.",
        key="f5_dashboard_scope",
    )
    if not escolha:
        st.warning("Selecione ao menos uma unidade.")
        return

    try:
        painel = app.painel_executivo(contexto=contexto, unidades=escolha)
    except Exception:  # noqa: BLE001
        _erro_generico("F5-DASH-READ")
        return

    f = painel.financeiro
    o = painel.operacional
    st.caption(
        "Dados consolidados somente das autoridades canônicas. CMV/margem são "
        "rotulados como estimativa atual quando dependem da ficha/custo vigente."
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Vendas reconhecidas", _dinheiro(f.vendas_reconhecidas))
    c2.metric("Ticket médio", _dinheiro(f.ticket_medio))
    c3.metric("Pagamentos recebidos", _dinheiro(f.pagamentos_pagos))
    c4.metric("Saldo pendente", _dinheiro(f.pagamentos_pendentes))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Pedidos", str(o.pedidos))
    c6.metric("Usuários ativos", str(o.usuarios_ativos))
    c7.metric("Integrações homologadas", f"{o.integracoes_homologadas}/{o.integracoes_configuradas}")
    c8.metric("Recebido em dinheiro", _dinheiro(f.recebido_dinheiro))

    c9, c10, c11 = st.columns(3)
    c9.metric("CMV estimado atual", _dinheiro(f.cmv_estimado_atual))
    c10.metric("Margem estimada atual", _dinheiro(f.margem_estimada_atual))
    c11.metric("Cobertura do CMV", f"{f.cobertura_cmv_itens_pct:.1f}%")

    st.subheader("Estoque")
    e1, e2 = st.columns(2)
    e1.metric("Saldo físico agregado", f"{o.estoque_fisico_total:,.3f}")
    e2.metric("Saldo reservado agregado", f"{o.estoque_reservado_total:,.3f}")

    st.subheader("Delivery / Entrega")
    if o.entregas_por_status:
        st.dataframe(
            pd.DataFrame(
                [{"Status": status, "Quantidade": total} for status, total in o.entregas_por_status]
            ),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.caption("Nenhuma entrega registrada no escopo selecionado.")


def _render_empresa_unidades(
    app: AplicacaoAdministracaoProprietarioV1,
    *,
    identidade: IdentidadeUsuario,
    session_factory: Callable[[], Session],
) -> None:
    contexto = _contexto(identidade)
    try:
        empresa = app.obter_empresa(contexto=contexto)
        unidades = app.listar_unidades(contexto=contexto)
    except Exception:  # noqa: BLE001
        _erro_generico("F5-CADASTRO-READ")
        return

    st.subheader("Empresa")
    with st.form("f5_empresa_form", clear_on_submit=False):
        nome = st.text_input("Nome da empresa", value=empresa.nome_exibicao)
        moeda = st.text_input("Moeda", value=empresa.moeda, max_chars=3)
        timezone = st.text_input("Timezone", value=empresa.timezone)
        ativa = st.checkbox("Empresa ativa", value=empresa.ativa)
        pin = st.text_input(
            "PIN administrativo para salvar empresa",
            type="password",
            max_chars=8,
            autocomplete="one-time-code",
        )
        salvar = st.form_submit_button("Salvar empresa", type="primary")
    if salvar:
        if not _pin_ok(
            identidade=identidade,
            pin=pin,
            session_factory=session_factory,
            permissao=Permissao.CONFIGURACAO_ALTERAR,
        ):
            st.error("PIN administrativo inválido ou sem permissão.")
        else:
            try:
                atualizada = app.atualizar_empresa(
                    contexto=contexto,
                    empresa=EmpresaAdministrativa(
                        tenant_id=empresa.tenant_id,
                        nome_exibicao=nome,
                        moeda=moeda,
                        timezone=timezone,
                        ativa=ativa,
                        versao=empresa.versao,
                    ),
                    versao_esperada=empresa.versao,
                )
                st.success(f"Empresa atualizada. Versão {atualizada.versao}.")
                st.rerun()
            except Exception:  # noqa: BLE001
                _erro_generico("F5-EMPRESA-WRITE")

    st.divider()
    st.subheader("Matriz e filiais")
    if unidades:
        tabela = pd.DataFrame(
            [
                {
                    "Unidade": u.unidade_id,
                    "Código": u.codigo,
                    "Nome": u.nome_fantasia,
                    "Tipo": u.tipo,
                    "Ativa": u.ativa,
                    "Versão": u.versao,
                }
                for u in unidades
            ]
        )
        st.dataframe(tabela, hide_index=True, use_container_width=True)

        selecionada_id = st.selectbox(
            "Editar unidade",
            options=[u.unidade_id for u in unidades],
            format_func=lambda uid: next(
                f"{u.nome_fantasia} · {uid}" for u in unidades if u.unidade_id == uid
            ),
            key="f5_unidade_editar",
        )
        unidade = next(u for u in unidades if u.unidade_id == selecionada_id)
        with st.form("f5_unidade_edit_form", clear_on_submit=False):
            col1, col2 = st.columns(2)
            with col1:
                codigo = st.text_input("Código", value=unidade.codigo)
                nome_u = st.text_input("Nome fantasia", value=unidade.nome_fantasia)
                tipo = st.selectbox(
                    "Tipo",
                    options=["matriz", "filial", "unidade"],
                    index=["matriz", "filial", "unidade"].index(unidade.tipo),
                )
                doc = st.text_input(
                    "Documento fiscal",
                    value=unidade.documento_fiscal or "",
                )
            with col2:
                email = st.text_input("E-mail comercial", value=unidade.email or "")
                telefone = st.text_input(
                    "Telefone comercial",
                    value=unidade.telefone or "",
                )
                ativa_u = st.checkbox("Unidade ativa", value=unidade.ativa)
                horario = st.text_area(
                    "Horários de funcionamento",
                    value=str(unidade.horarios.get("descricao", "")),
                    help="Descrição operacional pública; não use credenciais.",
                )
            endereco = st.text_area(
                "Endereço comercial",
                value=str(unidade.endereco.get("descricao", "")),
            )
            pin_u = st.text_input(
                "PIN administrativo para salvar unidade",
                type="password",
                max_chars=8,
                autocomplete="one-time-code",
            )
            salvar_u = st.form_submit_button("Salvar unidade", type="primary")
        if salvar_u:
            if not _pin_ok(
                identidade=identidade,
                pin=pin_u,
                session_factory=session_factory,
                permissao=Permissao.CONFIGURACAO_ALTERAR,
            ):
                st.error("PIN administrativo inválido ou sem permissão.")
            else:
                try:
                    app.atualizar_unidade(
                        contexto=contexto,
                        unidade=UnidadeAdministrativa(
                            tenant_id=contexto.tenant_id,
                            unidade_id=unidade.unidade_id,
                            codigo=codigo,
                            nome_fantasia=nome_u,
                            tipo=tipo,
                            documento_fiscal=doc or None,
                            telefone=telefone or None,
                            email=email or None,
                            endereco={"descricao": endereco.strip()} if endereco.strip() else {},
                            horarios={"descricao": horario.strip()} if horario.strip() else {},
                            ativa=ativa_u,
                            versao=unidade.versao,
                        ),
                        versao_esperada=unidade.versao,
                    )
                    st.success("Unidade atualizada.")
                    st.rerun()
                except Exception:  # noqa: BLE001
                    _erro_generico("F5-UNIDADE-WRITE")

    with st.expander("Cadastrar nova filial/unidade", expanded=False):
        with st.form("f5_nova_unidade_form", clear_on_submit=True):
            unidade_id = st.text_input(
                "ID técnico da unidade",
                placeholder="Ex.: loja-centro",
                help="Identificador estável. Não use CNPJ, telefone ou segredo.",
            )
            codigo_novo = st.text_input("Código comercial", placeholder="CENTRO")
            nome_novo = st.text_input("Nome fantasia")
            tipo_novo = st.selectbox("Tipo", ["filial", "matriz", "unidade"])
            endereco_novo = st.text_area("Endereço comercial")
            horario_novo = st.text_area("Horários de funcionamento")
            pin_novo = st.text_input(
                "PIN administrativo para criar unidade",
                type="password",
                max_chars=8,
                autocomplete="one-time-code",
            )
            criar = st.form_submit_button("Criar unidade", type="primary")
        if criar:
            if not _pin_ok(
                identidade=identidade,
                pin=pin_novo,
                session_factory=session_factory,
                permissao=Permissao.CONFIGURACAO_ALTERAR,
            ):
                st.error("PIN administrativo inválido ou sem permissão.")
            else:
                try:
                    app.criar_unidade(
                        contexto=contexto,
                        unidade=UnidadeAdministrativa(
                            tenant_id=contexto.tenant_id,
                            unidade_id=unidade_id,
                            codigo=codigo_novo,
                            nome_fantasia=nome_novo,
                            tipo=tipo_novo,
                            endereco=(
                                {"descricao": endereco_novo.strip()}
                                if endereco_novo.strip()
                                else {}
                            ),
                            horarios=(
                                {"descricao": horario_novo.strip()}
                                if horario_novo.strip()
                                else {}
                            ),
                        ),
                    )
                    st.success("Nova unidade cadastrada e vinculada ao tenant.")
                    st.rerun()
                except Exception:  # noqa: BLE001
                    _erro_generico("F5-UNIDADE-CREATE")


def _render_financeiro(
    app: AplicacaoAdministracaoProprietarioV1,
    *,
    identidade: IdentidadeUsuario,
    session_factory: Callable[[], Session],
) -> None:
    contexto = _contexto(identidade)
    try:
        unidades = app.listar_unidades(contexto=contexto)
    except Exception:  # noqa: BLE001
        _erro_generico("F5-FIN-UNIDADES")
        return
    if not unidades:
        st.info("Cadastre uma unidade antes de configurar parâmetros financeiros.")
        return

    uid = st.selectbox(
        "Unidade financeira",
        options=[u.unidade_id for u in unidades],
        format_func=lambda valor: next(
            f"{u.nome_fantasia} · {valor}" for u in unidades if u.unidade_id == valor
        ),
        key="f5_fin_unidade",
    )
    try:
        config = app.obter_configuracao(contexto=contexto, unidade_id=uid)
    except Exception:  # noqa: BLE001
        _erro_generico("F5-FIN-CONFIG")
        return

    st.caption(
        "Gateways, tokens, contas PIX e credenciais continuam no Control Plane protegido. "
        "Esta seção armazena somente parâmetros não secretos."
    )
    try:
        st.page_link(
            "pages/7_Integracoes_e_Credenciais.py",
            label="Abrir Integrações e Credenciais protegidas",
            icon="🔑",
            width="stretch",
        )
    except (KeyError, StreamlitPageNotFoundError):
        # Compatibilidade com execução direta da página em gates/browser.
        # Nesse modo a página irmã pode não fazer parte da navegação registrada.
        st.markdown(
            "🔑 [Abrir Integrações e Credenciais protegidas](./Integracoes_e_Credenciais)"
        )

    with st.form("f5_fin_config_form", clear_on_submit=False):
        formas = st.multiselect(
            "Formas de pagamento habilitadas",
            options=list(_FORMAS_PAGAMENTO),
            default=list(config.formas_pagamento),
        )
        taxa = st.number_input(
            "Taxa de serviço (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(config.taxa_servico_percentual),
            step=0.1,
        )
        aceita_entrega = st.checkbox(
            "Permitir pagamento na entrega",
            value=bool(
                config.parametros_operacionais.get(
                    "aceita_pagamento_na_entrega",
                    False,
                )
            ),
        )
        taxa_embalagem = st.number_input(
            "Taxa pública de embalagem (R$)",
            min_value=0.0,
            value=float(cast(Any, config.politica_financeira.get("taxa_embalagem", 0) or 0)),
            step=0.5,
        )
        pin = st.text_input(
            "PIN administrativo para salvar parâmetros financeiros",
            type="password",
            max_chars=8,
            autocomplete="one-time-code",
        )
        salvar = st.form_submit_button("Salvar parâmetros financeiros", type="primary")

    if salvar:
        if not _pin_ok(
            identidade=identidade,
            pin=pin,
            session_factory=session_factory,
            permissao=Permissao.CONFIGURACAO_ALTERAR,
        ):
            st.error("PIN administrativo inválido ou sem permissão.")
            return
        try:
            taxa_decimal = Decimal(str(taxa))
            embalagem_decimal = Decimal(str(taxa_embalagem))
            app.salvar_configuracao(
                contexto=contexto,
                configuracao=ConfiguracaoEstabelecimento(
                    tenant_id=contexto.tenant_id,
                    unidade_id=uid,
                    formas_pagamento=tuple(formas),
                    taxa_servico_percentual=taxa_decimal,
                    parametros_operacionais={
                        **dict(config.parametros_operacionais),
                        "aceita_pagamento_na_entrega": aceita_entrega,
                    },
                    politica_financeira={
                        **dict(config.politica_financeira),
                        "taxa_embalagem": str(embalagem_decimal),
                    },
                    versao=config.versao,
                ),
                versao_esperada=config.versao,
            )
            st.success("Parâmetros financeiros atualizados.")
            st.rerun()
        except (InvalidOperation, ValueError):
            st.error("Parâmetro financeiro inválido.")
        except Exception:  # noqa: BLE001
            _erro_generico("F5-FIN-WRITE")



def _render_impressao_config(
    app: AplicacaoAdministracaoProprietarioV1,
    *,
    identidade: IdentidadeUsuario,
    session_factory: Callable[[], Session],
) -> None:
    contexto = _contexto(identidade)
    try:
        unidades = app.listar_unidades(contexto=contexto)
    except Exception:  # noqa: BLE001
        _erro_generico("F9D-PRINT-UNIDADES")
        return
    if not unidades:
        st.info("Cadastre uma unidade antes de configurar impressão.")
        return

    uid = st.selectbox(
        "Unidade de impressão",
        options=[u.unidade_id for u in unidades],
        format_func=lambda valor: next(
            f"{u.nome_fantasia} · {valor}" for u in unidades if u.unidade_id == valor
        ),
        key="f9d_print_unit",
    )
    try:
        config = app.obter_configuracao(contexto=contexto, unidade_id=uid)
    except Exception:  # noqa: BLE001
        _erro_generico("F9D-PRINT-CONFIG")
        return

    bloco = config.parametros_operacionais.get("impressao", {})
    destinos = bloco.get("destinos", []) if isinstance(bloco, dict) else []
    linhas = [
        {
            "setor_id": str(item.get("setor_id", "")),
            "impressora_id": str(item.get("impressora_id", "")),
            "max_tentativas": int(item.get("max_tentativas", 3)),
            "ativo": bool(item.get("ativo", True)),
        }
        for item in destinos
        if isinstance(item, dict)
    ]
    st.caption(
        "Adapter comercial RAW TCP/JetDirect. Use endpoints como tcp://192.168.0.50:9100. "
        "Não informe usuário, senha, token ou outro segredo."
    )
    editado = st.data_editor(
        pd.DataFrame(linhas, columns=["setor_id", "impressora_id", "max_tentativas", "ativo"]),
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        key="f9d_print_destinations",
    )
    pin = st.text_input(
        "PIN administrativo para salvar impressão",
        type="password",
        max_chars=8,
        autocomplete="one-time-code",
        key="f9d_print_pin",
    )
    if st.button("Salvar destinos de impressão", type="primary", key="f9d_print_save"):
        if not _pin_ok(
            identidade=identidade,
            pin=pin,
            session_factory=session_factory,
            permissao=Permissao.CONFIGURACAO_ALTERAR,
        ):
            st.error("PIN administrativo inválido ou sem permissão.")
            return
        novos: list[dict[str, object]] = []
        try:
            for row in editado.to_dict(orient="records"):
                setor = str(row.get("setor_id", "")).strip()
                endpoint = str(row.get("impressora_id", "")).strip()
                if not setor and not endpoint:
                    continue
                if not setor or not endpoint.startswith("tcp://"):
                    raise ValueError("destino_impressao_invalido")
                max_tentativas = int(row.get("max_tentativas", 3))
                if max_tentativas < 1 or max_tentativas > 10:
                    raise ValueError("max_tentativas_invalido")
                novos.append(
                    {
                        "provider": "raw_tcp",
                        "setor_id": setor,
                        "impressora_id": endpoint,
                        "max_tentativas": max_tentativas,
                        "ativo": bool(row.get("ativo", True)),
                    }
                )
            app.salvar_configuracao(
                contexto=contexto,
                configuracao=ConfiguracaoEstabelecimento(
                    tenant_id=contexto.tenant_id,
                    unidade_id=uid,
                    formas_pagamento=config.formas_pagamento,
                    taxa_servico_percentual=config.taxa_servico_percentual,
                    parametros_operacionais={
                        **dict(config.parametros_operacionais),
                        "impressao": {"destinos": novos},
                    },
                    politica_financeira=dict(config.politica_financeira),
                    versao=config.versao,
                ),
                versao_esperada=config.versao,
            )
            st.success("Destinos de impressão atualizados.")
            st.rerun()
        except (TypeError, ValueError):
            st.error("Configuração de impressão inválida.")
        except Exception:  # noqa: BLE001
            _erro_generico("F9D-PRINT-WRITE")

def _render_usuarios(
    app: AplicacaoAdministracaoProprietarioV1,
    *,
    identidade: IdentidadeUsuario,
    session_factory: Callable[[], Session],
) -> None:
    contexto = _contexto(identidade)
    try:
        usuarios = app.listar_usuarios(contexto=contexto)
        unidades = app.listar_unidades(contexto=contexto)
    except Exception:  # noqa: BLE001
        _erro_generico("F5-USERS-READ")
        return

    st.caption(
        "As permissões são derivadas da matriz canônica de papéis. "
        "A Fase 5 não cria ACL paralela por usuário."
    )
    if usuarios:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "E-mail": u.email,
                        "Ativo": u.ativo,
                        "Papéis": ", ".join(u.papeis),
                        "Unidades": ", ".join(u.unidades),
                        "Padrão": u.unidade_padrao,
                        "Admin sensível": u.acesso_admin_sensivel,
                    }
                    for u in usuarios
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )

    with st.expander("Matriz efetiva de papéis e permissões"):
        linhas = []
        for papel, permissoes in MATRIZ_PADRAO.items():
            linhas.append(
                {
                    "Papel": papel.value,
                    "Permissões": ", ".join(sorted(p.value for p in permissoes)),
                }
            )
        st.dataframe(pd.DataFrame(linhas), hide_index=True, use_container_width=True)

    if usuarios:
        escolhido = st.selectbox(
            "Editar usuário",
            options=[u.usuario_id for u in usuarios],
            format_func=lambda uid: next(u.email for u in usuarios if u.usuario_id == uid),
            key="f5_usuario_editar",
        )
        usuario = next(u for u in usuarios if u.usuario_id == escolhido)
        with st.form("f5_usuario_edit_form", clear_on_submit=False):
            papeis = st.multiselect(
                "Papéis",
                options=[papel.value for papel in Papel],
                default=list(usuario.papeis),
            )
            unidades_sel = st.multiselect(
                "Unidades permitidas",
                options=[u.unidade_id for u in unidades],
                default=list(usuario.unidades),
            )
            unidade_padrao = st.selectbox(
                "Unidade padrão",
                options=unidades_sel or [usuario.unidade_padrao],
                index=(
                    (unidades_sel or [usuario.unidade_padrao]).index(usuario.unidade_padrao)
                    if usuario.unidade_padrao in (unidades_sel or [usuario.unidade_padrao])
                    else 0
                ),
            )
            ativo = st.checkbox("Usuário ativo", value=usuario.ativo)
            admin_sensivel = st.checkbox(
                "Autorizar acesso administrativo sensível",
                value=usuario.acesso_admin_sensivel,
            )
            nova_senha = st.text_input(
                "Nova senha (opcional)",
                type="password",
                autocomplete="new-password",
            )
            pin = st.text_input(
                "Seu PIN administrativo para salvar usuário",
                type="password",
                max_chars=8,
                autocomplete="one-time-code",
            )
            salvar = st.form_submit_button("Salvar usuário", type="primary")
        if salvar:
            if not _pin_ok(
                identidade=identidade,
                pin=pin,
                session_factory=session_factory,
                permissao=Permissao.PERMISSAO_GERENCIAR,
            ):
                st.error("PIN administrativo inválido ou sem permissão.")
            else:
                try:
                    app.atualizar_usuario(
                        contexto=contexto,
                        usuario_id=usuario.usuario_id,
                        papeis=[Papel(item) for item in papeis],
                        unidades_permitidas=unidades_sel,
                        unidade_padrao_id=unidade_padrao,
                        ativo=ativo,
                        acesso_admin_sensivel=admin_sensivel,
                        nova_senha=nova_senha or None,
                    )
                    st.success("Usuário atualizado.")
                    st.rerun()
                except Exception:  # noqa: BLE001
                    _erro_generico("F5-USERS-WRITE")

    with st.expander("Criar usuário", expanded=False):
        with st.form("f5_usuario_create_form", clear_on_submit=True):
            email = st.text_input("E-mail do novo usuário")
            senha = st.text_input(
                "Senha inicial",
                type="password",
                autocomplete="new-password",
            )
            papeis_novos = st.multiselect(
                "Papéis do novo usuário",
                options=[papel.value for papel in Papel],
            )
            unidades_novas = st.multiselect(
                "Unidades do novo usuário",
                options=[u.unidade_id for u in unidades],
            )
            unidade_padrao_nova = st.selectbox(
                "Unidade padrão do novo usuário",
                options=unidades_novas or [""],
            )
            acesso_admin = st.checkbox("Acesso administrativo sensível")
            admin_pin = st.text_input(
                "PIN inicial do novo administrador (opcional)",
                type="password",
                max_chars=8,
                autocomplete="new-password",
            )
            pin_operador = st.text_input(
                "Seu PIN administrativo para criar usuário",
                type="password",
                max_chars=8,
                autocomplete="one-time-code",
            )
            criar = st.form_submit_button("Criar usuário", type="primary")
        if criar:
            if not _pin_ok(
                identidade=identidade,
                pin=pin_operador,
                session_factory=session_factory,
                permissao=Permissao.USUARIO_GERENCIAR,
            ):
                st.error("PIN administrativo inválido ou sem permissão.")
            else:
                try:
                    app.criar_usuario(
                        contexto=contexto,
                        email=email,
                        password=senha,
                        unidade_padrao_id=unidade_padrao_nova,
                        papeis=[Papel(item) for item in papeis_novos],
                        unidades_permitidas=unidades_novas,
                        acesso_admin_sensivel=acesso_admin,
                        admin_pin=admin_pin or None,
                    )
                    st.success("Usuário criado.")
                    st.rerun()
                except Exception:  # noqa: BLE001
                    _erro_generico("F5-USERS-CREATE")


def _identidade_no_escopo_admin(
    identidade: IdentidadeUsuario,
    *,
    unidade_id: str,
) -> IdentidadeUsuario:
    if unidade_id == identidade.unidade_id:
        return identidade
    if Papel.ADMINISTRADOR in identidade.papeis:
        return replace(
            identidade,
            unidade_id=unidade_id,
            unidades_permitidas=frozenset(
                {*identidade.unidades_permitidas, unidade_id}
            ),
        )
    return identidade.no_escopo_ativo(
        tenant_id=identidade.tenant_id,
        unidade_id=unidade_id,
    )


def _render_integracoes(
    app: AplicacaoAdministracaoProprietarioV1,
    *,
    identidade: IdentidadeUsuario,
    session_factory: Callable[[], Session],
) -> None:
    contexto = _contexto(identidade)
    try:
        unidades = app.listar_unidades(contexto=contexto)
        integracoes = app.listar_integracoes(
            contexto=contexto,
            unidades=[u.unidade_id for u in unidades],
        )
    except Exception:  # noqa: BLE001
        _erro_generico("F5-INTEGRACOES-READ")
        return
    st.caption(
        "Somente estado e metadados públicos são mostrados no resumo. "
        "Tokens, chaves e segredos nunca são reexibidos."
    )
    if integracoes:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Unidade": item.unidade_id,
                        "Serviço": item.servico,
                        "Provedor": item.provedor,
                        "Estado": item.estado,
                        "Habilitada": item.habilitada,
                        "Homologada": item.homologada,
                    }
                    for item in integracoes
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("Nenhuma integração configurada nas unidades cadastradas.")

    if not unidades:
        return
    unidade_id = st.selectbox(
        "Unidade para gerenciar integrações",
        options=[u.unidade_id for u in unidades],
        format_func=lambda uid: next(
            f"{u.nome_fantasia} · {uid}" for u in unidades if u.unidade_id == uid
        ),
        key="f5_integracoes_unidade",
    )
    st.caption(
        "O gerenciamento abaixo usa o mesmo Control Plane e o mesmo Vault da "
        "unidade selecionada; nenhum segredo é copiado para a Fase 5."
    )
    with st.expander(
        f"Gerenciar integrações de {unidade_id}",
        expanded=False,
    ):
        render_integracoes_admin(
            identidade=_identidade_no_escopo_admin(
                identidade,
                unidade_id=unidade_id,
            ),
            session_factory=session_factory,
        )


def _render_auditoria(
    app: AplicacaoAdministracaoProprietarioV1,
    *,
    identidade: IdentidadeUsuario,
) -> None:
    contexto = _contexto(identidade)
    try:
        unidades = app.listar_unidades(contexto=contexto)
    except Exception:  # noqa: BLE001
        _erro_generico("F5-AUDIT-UNIDADES")
        return
    if not unidades:
        return
    uid = st.selectbox(
        "Unidade da auditoria",
        options=[u.unidade_id for u in unidades],
        key="f5_audit_unit",
    )
    try:
        eventos = app.listar_auditoria(
            contexto=contexto,
            unidade_id=uid,
            limite=200,
        )
    except Exception:  # noqa: BLE001
        _erro_generico("F5-AUDIT-READ")
        return

    if not eventos:
        st.caption("Nenhum evento de auditoria encontrado para a unidade.")
        return
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Data": evento.timestamp,
                    "Usuário": evento.usuario_id,
                    "Ação": evento.acao,
                    "Recurso": evento.recurso_tipo,
                    "Resultado": evento.resultado,
                    "Correlation": evento.correlation_id,
                }
                for evento in eventos
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )


def render_admin_proprietario(
    *,
    identidade: IdentidadeUsuario,
    session_factory: Callable[[], Session],
) -> None:
    app = AplicacaoAdministracaoProprietarioV1(session_factory)
    _registrar_acesso_uma_vez(app, identidade=identidade)

    st.subheader("Centro Administrativo")
    st.caption(
        "Visão executiva, matriz/filiais, parâmetros financeiros, usuários, "
        "integrações e auditoria no mesmo escopo protegido."
    )

    abas = st.tabs(
        [
            "📊 Visão executiva",
            "🏢 Empresa e unidades",
            "💳 Financeiro",
            "🖨️ Impressão",
            "👥 Usuários e permissões",
            "🔌 Integrações e saúde",
            "🧾 Auditoria",
        ]
    )
    with abas[0]:
        _render_dashboard(app, identidade=identidade)
    with abas[1]:
        _render_empresa_unidades(
            app,
            identidade=identidade,
            session_factory=session_factory,
        )
    with abas[2]:
        _render_financeiro(
            app,
            identidade=identidade,
            session_factory=session_factory,
        )
    with abas[3]:
        _render_impressao_config(
            app,
            identidade=identidade,
            session_factory=session_factory,
        )
    with abas[4]:
        _render_usuarios(
            app,
            identidade=identidade,
            session_factory=session_factory,
        )
    with abas[5]:
        _render_integracoes(
            app,
            identidade=identidade,
            session_factory=session_factory,
        )
    with abas[6]:
        _render_auditoria(app, identidade=identidade)
