"""Boundary do forecasting e alertas legados de estoque."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from application.notificacoes_internas import despachar_alerta_estoque
from core.notificacoes_internas.flags import internal_notifications_v1_enabled
from core.seguranca.contexto import ContextoExecucao
from infra.legacy_product_scope import listar_insumos_legados
from infra.notificacoes_internas import (
    EntregaWhatsAppNotificacaoInterna,
    RepositorioNotificacoesInternasSQLAlchemy,
)


class AplicacaoForecastingEstoqueV1:
    """Executa a varredura e os despachos com a semântica original."""

    def executar(
        self,
        db_session: Session,
        *,
        tenant_id: str,
        unidade_id: str,
        contexto_notificacoes: Callable[[], ContextoExecucao],
        generate_content: Callable[..., Any],
        is_test_mode: bool,
        mock_whatsapp_send: Callable[[str, str], dict[str, Any]],
        listar_destinatarios_legados: Callable[[], Sequence[Any]],
        enviar_whatsapp_control_plane: Callable[..., str],
        data_referencia: Callable[[], date] = date.today,
    ) -> str:
        insumos = listar_insumos_legados(
            db_session,
            tenant_id=tenant_id,
            unidade_id=unidade_id,
        )
        usar_diretorio_canonico = internal_notifications_v1_enabled()
        diretorio_notificacoes = None

        if usar_diretorio_canonico:
            try:
                contexto = contexto_notificacoes()
                if (
                    contexto.tenant_id != tenant_id
                    or contexto.unidade_id != unidade_id
                ):
                    raise PermissionError(
                        "escopo do forecasting diverge da identidade ativa"
                    )
                diretorio_notificacoes = RepositorioNotificacoesInternasSQLAlchemy(
                    db_session
                )
                destinatarios_canonicos = diretorio_notificacoes.listar_alertas_estoque(
                    contexto=contexto
                )
            except Exception:  # noqa: BLE001 - preserva retorno legado fail-closed
                return (
                    "❌ Não foi possível resolver os destinatários de alertas "
                    "da unidade ativa."
                )
            if not destinatarios_canonicos:
                return (
                    "⚠️ Nenhum destinatário interno está configurado para "
                    "receber alertas nesta unidade."
                )
        else:
            destinatarios_legados = listar_destinatarios_legados()
            if not destinatarios_legados:
                return (
                    "⚠️ Nenhum gerente ou administrador está configurado "
                    "para receber alertas na Aba 4."
                )

        resumo_estoque = ""
        for i in insumos:
            val_info = (
                f", Validade: {i.data_validade.strftime('%d/%m/%Y')} "
                f"(Aviso {i.dias_alerta_vencimento} dias antes)"
                if i.data_validade
                else ""
            )
            resumo_estoque += (
                f"- {i.nome}: Saldo Atual = {i.saldo_atual} "
                f"{i.unidade_medida}, Mínimo = {i.estoque_minimo}"
                f"{val_info}\n"
            )

        prompt_forecast = f"""
    Você é o assistente de inteligência preditiva de um ERP gastronômico de alta performance.
    Analise o estado atual do almoxarifado abaixo e determine se há algum ingrediente com risco iminente de esgotamento OU próximo da data de validade com base no ritmo operacional:
    {resumo_estoque}

    Retorne APENAS um array JSON puro (sem markdown) com os insumos em risco crítico (quantidade ou validade):
    [
      {{"insumo": "Nome do Insumo", "previsao_esgotamento": "Sábado às 20h ou Vence em 5 dias", "mensagem_alerta": "Estoque crítico! / Sugestão de Promoção!"}}
    ]
    Se nenhum item estiver em risco, retorne um array vazio [].
    """

        try:
            resp = generate_content(contents=prompt_forecast)
            texto_limpo = (
                resp.text.strip().replace("```json", "").replace("```", "").strip()
            )
            alertas_ia = json.loads(texto_limpo)

            if not alertas_ia:
                return (
                    "✅ Estoque operacional seguro e validades sob controle. "
                    "Nenhum alerta preditivo gerado."
                )

            total_enviados = 0
            if usar_diretorio_canonico:
                assert diretorio_notificacoes is not None

                def _sender_teste(
                    destinatario: str,
                    texto: str,
                    idempotency_key: str,
                ) -> str:
                    envio = mock_whatsapp_send(destinatario, texto)
                    if not envio["ok"]:
                        raise RuntimeError("falha simulada de WhatsApp")
                    return f"mock:{idempotency_key}"

                entrega = EntregaWhatsAppNotificacaoInterna(
                    session=db_session,
                    diretorio=diretorio_notificacoes,
                    sender=_sender_teste if is_test_mode else None,
                )
                for alerta in alertas_ia:
                    texto_msg = self._texto_alerta(alerta)
                    resultados = despachar_alerta_estoque(
                        contexto=contexto,
                        diretorio=diretorio_notificacoes,
                        entrega=entrega,
                        alerta=alerta,
                        texto=texto_msg,
                        data_referencia=data_referencia(),
                    )
                    total_enviados += sum(
                        1 for resultado in resultados if resultado.enviado
                    )
                if total_enviados == 0:
                    return (
                        "❌ Os alertas foram gerados, mas nenhum destinatário "
                        "da unidade recebeu a notificação."
                    )
            else:
                for alerta in alertas_ia:
                    texto_msg = self._texto_alerta(alerta)
                    for contato in destinatarios_legados:
                        if is_test_mode:
                            envio_mock = mock_whatsapp_send(
                                contato.whatsapp,
                                texto_msg,
                            )
                            if envio_mock["ok"]:
                                total_enviados += 1
                        else:
                            from infra.integracoes.idempotencia_alertas import (
                                chave_idempotencia_alerta_estoque,
                            )

                            mensagem_id = enviar_whatsapp_control_plane(
                                destinatario=contato.whatsapp,
                                texto=texto_msg,
                                idempotency_key=chave_idempotencia_alerta_estoque(
                                    contato_id=contato.id,
                                    alerta=alerta,
                                    data_referencia=data_referencia(),
                                ),
                            )
                            if mensagem_id:
                                total_enviados += 1

            return (
                f"🚀 Análise concluída com sucesso! {len(alertas_ia)} alertas "
                f"preditivos (Estoque/Validade) disparados para "
                f"{total_enviados} gestores via WhatsApp."
            )
        except Exception:  # noqa: BLE001 - preserva retorno legado fail-closed
            return (
                "❌ Não foi possível concluir o forecasting ou enviar os alertas. "
                "Verifique as integrações Gemini e Meta/WhatsApp desta unidade."
            )

    @staticmethod
    def _texto_alerta(alerta: Any) -> str:
        return (
            "🚨 *ALERTA PREDITIVO DE ESTOQUE (F&M AI FOOD)* 🚨\n\n"
            f"Item: *{alerta['insumo']}*\n"
            f"Risco/Previsão: *{alerta['previsao_esgotamento']}*\n"
            f"Status: {alerta['mensagem_alerta']}\n\n"
            "*Acesse o painel para reposição ou criar promoção de queima.*"
        )
