"""Composition root comercial do Agente Inteligente de Atendimento V1."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from application.ai_router_runtime import construir_ai_model_router
from core.ai_router import CapabilityIA, ConteudoAudioIA, SolicitacaoIA
from core.assistente_atendimento.atendimento_modelos import (
    EstadoAtendimento,
    ModalidadePedidoAtendimento,
    ProdutoCatalogoAtendimento,
    ResultadoAtendimento,
)
from core.assistente_atendimento.atendimento_servicos import (
    ServicoAssistenteAtendimento,
)
from core.assistente_atendimento.checkout_adapter import CheckoutAssistenteV1
from core.assistente_atendimento.contexto import ContextoAtendimento
from core.assistente_atendimento.entradas import (
    EntradaAtendimento,
    ModalidadeEntrada,
)
from core.gerente_ia.erros import ErroGerenteIA
from core.pagamentos.modelos import MetodoPagamento
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import MATRIZ_PADRAO, Papel, Permissao
from infra.assistente_atendimento.clientes_sqlalchemy import (
    ClientesAtendimentoSQLAlchemy,
)
from infra.assistente_atendimento.entrega_maps import (
    CotadorEntregaAssistenteGoogleMaps,
)
from infra.assistente_atendimento.handoff_sqlalchemy import (
    HandoffAssistenteAuditSQLAlchemy,
)
from infra.gerente_ia.modelos_orm import DisponibilidadeProdutoORM
from infra.legacy_product_scope import listar_produtos_legados
from infra.seguranca.segredos_sqlalchemy import EncryptedSQLAlchemySecretStore

SessionFactory = Callable[[], Session]


def _contexto_agente(contexto_solicitante: ContextoExecucao) -> ContextoExecucao:
    """Cria principal técnico estreito preservando escopo e causalidade humana."""

    permissoes = set(MATRIZ_PADRAO[Papel.ATENDIMENTO])
    permissoes.add(Permissao.CLIENTE_EDITAR)

    return ContextoExecucao(
        tenant_id=contexto_solicitante.tenant_id,
        unidade_id=contexto_solicitante.unidade_id,
        usuario_id="assistente-atendimento-v1",
        papeis=frozenset({Papel.ATENDIMENTO}),
        permissoes=frozenset(permissoes),
        correlation_id=contexto_solicitante.correlation_id,
        solicitado_em=contexto_solicitante.solicitado_em,
        origem="assistente_atendimento_v1",
        causation_id=(
            contexto_solicitante.causation_id
            or contexto_solicitante.correlation_id
        ),
        request_id=contexto_solicitante.request_id,
        metadata=(("solicitante_usuario_id", contexto_solicitante.usuario_id),),
        unidades_permitidas=frozenset({contexto_solicitante.unidade_id}),
        identidade_sistema=True,
        motivo_sistema="atendimento digital governado solicitado no runtime comercial",
    )


def _valor(row, nome: str):
    if hasattr(row, nome):
        return getattr(row, nome)
    mapping = getattr(row, "_mapping", None)
    if mapping is not None and nome in mapping:
        return mapping[nome]
    raise KeyError(nome)


def _catalogo(
    session: Session,
    *,
    contexto: ContextoExecucao,
) -> tuple[ProdutoCatalogoAtendimento, ...]:
    rows = listar_produtos_legados(
        session,
        tenant_id=contexto.tenant_id,
        unidade_id=contexto.unidade_id,
    )

    pausados = {
        str(produto_id)
        for produto_id in session.scalars(
            select(DisponibilidadeProdutoORM.produto_id).where(
                DisponibilidadeProdutoORM.tenant_id == contexto.tenant_id,
                DisponibilidadeProdutoORM.unidade_id == contexto.unidade_id,
                DisponibilidadeProdutoORM.pausado.is_(True),
            )
        ).all()
    }

    produtos: list[ProdutoCatalogoAtendimento] = []
    for row in rows:
        produto_id = str(_valor(row, "id"))
        if produto_id in pausados:
            continue

        nome = str(_valor(row, "nome") or "").strip()
        preco = Decimal(str(_valor(row, "preco_venda") or "0"))
        if not nome or preco < 0:
            continue

        produtos.append(
            ProdutoCatalogoAtendimento(
                produto_id=produto_id,
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                nome=nome,
                preco=preco,
                ativo=True,
            )
        )

    return tuple(produtos)


def _prompt_interpretacao(
    *,
    nome_publico: str,
    mensagem: str,
    catalogo: tuple[ProdutoCatalogoAtendimento, ...],
) -> str:
    menu = "\n".join(
        f"- {produto.nome} | R$ {produto.preco:.2f}"
        for produto in catalogo
    )
    return (
        f"Você é {nome_publico}, agente digital de atendimento do estabelecimento.\n"
        "Sua tarefa nesta etapa é SOMENTE interpretar a intenção do cliente. "
        "Não confirme pagamento, não crie pedido e não invente produto, preço, "
        "desconto, disponibilidade, endereço ou status.\n"
        "Use exclusivamente nomes EXATOS do catálogo abaixo. Se o pedido for "
        "ambíguo ou não estiver no catálogo, mantenha o nome pedido pelo cliente; "
        "o serviço determinístico fará handoff fail-closed.\n"
        "Para modalidade, use somente retirada, entrega ou indefinida. "
        "Só copie endereco_texto quando o próprio cliente informou endereço.\n"
        "Retorne SOMENTE JSON puro, sem markdown, com exatamente este schema:\n"
        '{"cliente_nome":"nome informado ou Cliente",'
        '"itens":[{"nome_produto":"nome EXATO","quantidade":1}],'
        '"resposta_cliente":"resumo para conferência, sem afirmar pagamento",'
        '"modalidade":"retirada|entrega|indefinida",'
        '"endereco_texto":null}\n'
        f"CATÁLOGO AUTORIZADO:\n{menu}\n"
        f"MENSAGEM DO CLIENTE:\n{mensagem.strip()}"
    )


def _cep_no_texto(texto: str | None) -> str | None:
    if not texto:
        return None
    candidatos = re.findall(r"(?<!\d)(\d{5})[-\s]?(\d{3})(?!\d)", texto)
    if len(candidatos) != 1:
        return None
    return "".join(candidatos[0])


@dataclass(frozen=True)
class ResultadoRuntimeAssistente:
    contexto: ContextoAtendimento
    resultado: ResultadoAtendimento


class RuntimeAssistenteAtendimentoV1:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self._handoff = HandoffAssistenteAuditSQLAlchemy(session_factory)
        self._checkout = CheckoutAssistenteV1(session_factory=session_factory)

    def _servico(self) -> ServicoAssistenteAtendimento:
        return ServicoAssistenteAtendimento(
            checkout=self._checkout,
            handoff=self._handoff,
        )

    def _tentar_cotacao_do_texto(
        self,
        runtime: ResultadoRuntimeAssistente,
    ) -> ResultadoRuntimeAssistente:
        carrinho = runtime.resultado.carrinho
        if (
            carrinho is None
            or carrinho.modalidade is not ModalidadePedidoAtendimento.ENTREGA
            or runtime.resultado.estado
            is not EstadoAtendimento.AGUARDANDO_ENDERECO_ENTREGA
            or not carrinho.endereco_solicitado
        ):
            return runtime
        cep = _cep_no_texto(carrinho.endereco_solicitado)
        if cep is None:
            return runtime
        return self.cotar_entrega(
            runtime_anterior=runtime,
            endereco_texto=carrinho.endereco_solicitado,
            cep=cep,
        )

    def _interpretar_entrada(
        self,
        *,
        contexto: ContextoExecucao,
        conversa_id: str,
        mensagem_id: str,
        identificador_cliente: str,
        texto_interpretacao: str,
        nome_publico: str,
        entrada: EntradaAtendimento,
    ) -> ResultadoRuntimeAssistente:
        db = self._session_factory()
        try:
            clientes = ClientesAtendimentoSQLAlchemy(db)
            cliente = clientes.identificar_por_canal(
                contexto=contexto,
                canal="whatsapp",
                identificador_externo=identificador_cliente,
            )
            catalogo = _catalogo(db, contexto=contexto)
            if not catalogo:
                raise ErroGerenteIA("catalogo_indisponivel")

            secret_store = EncryptedSQLAlchemySecretStore(db)
            router = construir_ai_model_router(
                session=db,
                contexto=contexto,
                secret_store=secret_store,
            )
            roteado = router.executar(
                SolicitacaoIA(
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                    request_id=mensagem_id,
                    correlation_id=contexto.correlation_id,
                    capability=CapabilityIA.ATENDIMENTO_INTERPRETACAO,
                    conteudo=_prompt_interpretacao(
                        nome_publico=nome_publico,
                        mensagem=texto_interpretacao,
                        catalogo=catalogo,
                    ),
                )
            )
            raw = str(roteado.conteudo)
        finally:
            db.close()

        contexto_atendimento = ContextoAtendimento(
            contexto_execucao=contexto,
            conversa_id=conversa_id,
            canal="whatsapp",
            cliente=cliente,
        )
        runtime = ResultadoRuntimeAssistente(
            contexto=contexto_atendimento,
            resultado=self._servico().interpretar(
                contexto=contexto_atendimento,
                entrada=entrada,
                raw_ia=raw,
                catalogo=catalogo,
            ),
        )
        if cliente.cliente_ref is not None:
            return self._tentar_cotacao_do_texto(runtime)
        return runtime

    def interpretar_texto(
        self,
        *,
        contexto_solicitante: ContextoExecucao,
        conversa_id: str,
        mensagem_id: str,
        identificador_cliente: str,
        mensagem: str,
        nome_publico: str,
    ) -> ResultadoRuntimeAssistente:
        if not identificador_cliente.strip() or not mensagem.strip():
            raise ValueError("cliente e mensagem são obrigatórios")

        contexto = _contexto_agente(contexto_solicitante)
        entrada = EntradaAtendimento(
            mensagem_id=mensagem_id,
            modalidade=ModalidadeEntrada.TEXTO,
            texto_original=mensagem,
        )
        return self._interpretar_entrada(
            contexto=contexto,
            conversa_id=conversa_id,
            mensagem_id=mensagem_id,
            identificador_cliente=identificador_cliente,
            texto_interpretacao=entrada.texto_para_interpretacao,
            nome_publico=nome_publico,
            entrada=entrada,
        )

    def interpretar_audio(
        self,
        *,
        contexto_solicitante: ContextoExecucao,
        conversa_id: str,
        mensagem_id: str,
        identificador_cliente: str,
        audio: bytes,
        mime_type: str,
        nome_publico: str,
    ) -> ResultadoRuntimeAssistente:
        if not identificador_cliente.strip():
            raise ValueError("cliente é obrigatório")

        contexto = _contexto_agente(contexto_solicitante)
        db = self._session_factory()
        try:
            secret_store = EncryptedSQLAlchemySecretStore(db)
            router = construir_ai_model_router(
                session=db,
                contexto=contexto,
                secret_store=secret_store,
            )
            transcricao = router.executar(
                SolicitacaoIA(
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                    request_id=f"{mensagem_id}:transcricao",
                    correlation_id=contexto.correlation_id,
                    capability=CapabilityIA.ATENDIMENTO_TRANSCRICAO,
                    conteudo=ConteudoAudioIA(
                        audio=audio,
                        mime_type=mime_type,
                        instrucao=(
                            "Transcreva fielmente este áudio de atendimento em "
                            "português. Retorne somente a transcrição, sem resumo, "
                            "sem interpretação e sem adicionar informações."
                        ),
                    ),
                )
            )
            texto = str(transcricao.conteudo).strip()
            if not texto:
                raise ErroGerenteIA("transcricao_audio_vazia")
        finally:
            db.close()

        entrada = EntradaAtendimento(
            mensagem_id=mensagem_id,
            modalidade=ModalidadeEntrada.AUDIO,
            transcricao=texto,
        )
        return self._interpretar_entrada(
            contexto=contexto,
            conversa_id=conversa_id,
            mensagem_id=mensagem_id,
            identificador_cliente=identificador_cliente,
            texto_interpretacao=entrada.texto_para_interpretacao,
            nome_publico=nome_publico,
            entrada=entrada,
        )

    def registrar_cliente_minimo(
        self,
        *,
        runtime_anterior: ResultadoRuntimeAssistente,
        identificador_cliente: str,
    ) -> ResultadoRuntimeAssistente:
        contexto = runtime_anterior.contexto.contexto_execucao
        db = self._session_factory()
        try:
            with db.begin():
                cliente = ClientesAtendimentoSQLAlchemy(db).registrar_novo(
                    contexto=contexto,
                    canal=runtime_anterior.contexto.canal,
                    identificador_externo=identificador_cliente,
                )
        finally:
            db.close()

        if cliente.cliente_ref is None:
            raise RuntimeError("cliente CRM registrado sem referencia")

        novo_contexto, novo_resultado = self._servico().concluir_cadastro_cliente(
            contexto_anterior=runtime_anterior.contexto,
            resultado=runtime_anterior.resultado,
            cliente_ref=cliente.cliente_ref,
        )
        return self._tentar_cotacao_do_texto(
            ResultadoRuntimeAssistente(
                contexto=novo_contexto,
                resultado=novo_resultado,
            )
        )

    def definir_modalidade(
        self,
        *,
        runtime_anterior: ResultadoRuntimeAssistente,
        modalidade: ModalidadePedidoAtendimento,
    ) -> ResultadoRuntimeAssistente:
        atualizado = self._servico().definir_modalidade(
            resultado=runtime_anterior.resultado,
            modalidade=modalidade,
        )
        runtime = ResultadoRuntimeAssistente(
            contexto=runtime_anterior.contexto,
            resultado=atualizado,
        )
        return self._tentar_cotacao_do_texto(runtime)

    def cotar_entrega(
        self,
        *,
        runtime_anterior: ResultadoRuntimeAssistente,
        endereco_texto: str,
        cep: str,
    ) -> ResultadoRuntimeAssistente:
        cliente_ref = runtime_anterior.contexto.cliente.cliente_ref
        if cliente_ref is None:
            raise ValueError("cliente canônico obrigatório antes da cotação")
        contexto = runtime_anterior.contexto.contexto_execucao
        db = self._session_factory()
        try:
            secret_store = EncryptedSQLAlchemySecretStore(db)
            cotacao = CotadorEntregaAssistenteGoogleMaps(
                db,
                secret_store=secret_store,
            ).cotar(
                contexto=contexto,
                cliente_ref=cliente_ref,
                endereco_texto=endereco_texto,
                cep_informado=cep,
            )
        finally:
            db.close()

        atualizado = self._servico().aplicar_cotacao_entrega(
            contexto=runtime_anterior.contexto,
            resultado=runtime_anterior.resultado,
            cotacao=cotacao,
        )
        return ResultadoRuntimeAssistente(
            contexto=runtime_anterior.contexto,
            resultado=atualizado,
        )

    def confirmar(
        self,
        *,
        runtime_anterior: ResultadoRuntimeAssistente,
        confirmacao_cliente: bool,
        fingerprint_confirmado: str,
        metodo: MetodoPagamento,
        idempotency_key: str,
    ) -> ResultadoAtendimento:
        return self._servico().confirmar(
            contexto=runtime_anterior.contexto,
            resultado=runtime_anterior.resultado,
            confirmacao_cliente=confirmacao_cliente,
            fingerprint_confirmado=fingerprint_confirmado,
            metodo=metodo,
            idempotency_key=idempotency_key,
        )


def novo_contexto_solicitante(
    *,
    tenant_id: str,
    unidade_id: str,
    usuario_id: str,
    papeis,
    permissoes,
) -> ContextoExecucao:
    """Helper restrito a testes/composições sem uma IdentidadeUsuario disponível."""

    return ContextoExecucao(
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        usuario_id=usuario_id,
        papeis=frozenset(papeis),
        permissoes=frozenset(permissoes),
        correlation_id=str(uuid4()),
        solicitado_em=datetime.now(timezone.utc),
        origem="assistente_atendimento.runtime",
        unidades_permitidas=frozenset({unidade_id}),
    )
