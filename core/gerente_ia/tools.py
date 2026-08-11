"""Allowlist e validação estrita das tools do Gerente IA V1."""

from __future__ import annotations

from dataclasses import dataclass

from .erros import ErroGerenteIA
from .modelos import NaturezaTool, ToolGerenteIA, ValorPrimitivo


@dataclass(frozen=True)
class EspecificacaoTool:
    natureza: NaturezaTool
    permitidos: frozenset[str]
    obrigatorios: frozenset[str]


ESPECIFICACOES: dict[ToolGerenteIA, EspecificacaoTool] = {
    ToolGerenteIA.CONSULTAR_PEDIDOS: EspecificacaoTool(
        NaturezaTool.CONSULTA, frozenset({"status", "limite"}), frozenset()
    ),
    ToolGerenteIA.CONSULTAR_ATRASOS: EspecificacaoTool(
        NaturezaTool.CONSULTA,
        frozenset({"limite", "minutos_minimos"}),
        frozenset(),
    ),
    ToolGerenteIA.CONSULTAR_MESAS: EspecificacaoTool(
        NaturezaTool.CONSULTA, frozenset({"status", "limite"}), frozenset()
    ),
    ToolGerenteIA.CONSULTAR_COZINHA: EspecificacaoTool(
        NaturezaTool.CONSULTA, frozenset({"setor_id", "limite"}), frozenset()
    ),
    ToolGerenteIA.CONSULTAR_ENTREGAS: EspecificacaoTool(
        NaturezaTool.CONSULTA, frozenset({"status", "limite"}), frozenset()
    ),
    ToolGerenteIA.CONSULTAR_ESTOQUE: EspecificacaoTool(
        NaturezaTool.CONSULTA,
        frozenset({"criticos_apenas", "limite"}),
        frozenset(),
    ),
    ToolGerenteIA.SUGERIR_COMPRA: EspecificacaoTool(
        NaturezaTool.CONSULTA,
        frozenset({"dias_cobertura", "limite"}),
        frozenset(),
    ),
    ToolGerenteIA.GERAR_RELATORIO: EspecificacaoTool(
        NaturezaTool.CONSULTA,
        frozenset({"tipo", "janela_dias"}),
        frozenset({"tipo"}),
    ),
    ToolGerenteIA.ACOMPANHAR_CONVERSAO: EspecificacaoTool(
        NaturezaTool.CONSULTA,
        frozenset({"janela_dias", "canal"}),
        frozenset(),
    ),
    ToolGerenteIA.PREPARAR_CAMPANHA: EspecificacaoTool(
        NaturezaTool.RASCUNHO,
        frozenset({"canal", "finalidade", "objetivo", "texto_base", "idempotency_key"}),
        frozenset({"canal", "finalidade", "objetivo", "texto_base", "idempotency_key"}),
    ),
    ToolGerenteIA.PRIORIZAR_PEDIDO: EspecificacaoTool(
        NaturezaTool.ACAO_COM_CONFIRMAR,
        frozenset({"pedido_id", "prioridade", "motivo"}),
        frozenset({"pedido_id", "prioridade", "motivo"}),
    ),
    ToolGerenteIA.PAUSAR_PRODUTO: EspecificacaoTool(
        NaturezaTool.ACAO_COM_CONFIRMAR,
        frozenset({"produto_id", "motivo", "duracao_minutos"}),
        frozenset({"produto_id", "motivo"}),
    ),
}

_CAMPOS_ESCOPOS_PROIBIDOS = frozenset(
    {
        "tenant_id",
        "empresa_id",
        "unidade_id",
        "usuario_id",
        "papeis",
        "permissoes",
        "permission",
        "role",
        "sql",
        "query",
        "senha",
        "password",
        "token",
        "secret",
        "segredo",
        "api_key",
        "authorization",
        "confirmado",
        "aprovador",
        "tool",
        "comando",
    }
)


def validar_argumentos(
    tool: ToolGerenteIA, argumentos: dict[str, ValorPrimitivo]
) -> dict[str, ValorPrimitivo]:
    especificacao = ESPECIFICACOES.get(tool)
    if especificacao is None:
        raise ErroGerenteIA("tool_nao_permitida")
    recebidos = frozenset(argumentos)
    if recebidos & _CAMPOS_ESCOPOS_PROIBIDOS:
        raise ErroGerenteIA("argumento_de_escopo_proibido")
    extras = recebidos - especificacao.permitidos
    if extras:
        raise ErroGerenteIA("argumento_nao_permitido")
    faltantes = especificacao.obrigatorios - recebidos
    if faltantes:
        raise ErroGerenteIA("argumento_obrigatorio_ausente")

    normalizados = dict(argumentos)
    if "limite" in normalizados:
        limite = _inteiro(normalizados["limite"], "limite_invalido")
        if limite < 1 or limite > 100:
            raise ErroGerenteIA("limite_invalido")
        normalizados["limite"] = limite
    for campo in ("minutos_minimos", "dias_cobertura", "janela_dias", "duracao_minutos"):
        if campo in normalizados and normalizados[campo] is not None:
            valor = _inteiro(normalizados[campo], f"{campo}_invalido")
            if valor < 1 or valor > 3650:
                raise ErroGerenteIA(f"{campo}_invalido")
            normalizados[campo] = valor
    if "prioridade" in normalizados:
        prioridade = _inteiro(normalizados["prioridade"], "prioridade_invalida")
        if prioridade < 1 or prioridade > 10:
            raise ErroGerenteIA("prioridade_invalida")
        normalizados["prioridade"] = prioridade
    if "criticos_apenas" in normalizados and not isinstance(
        normalizados["criticos_apenas"], bool
    ):
        raise ErroGerenteIA("criticos_apenas_invalido")

    for campo in (
        "status",
        "setor_id",
        "tipo",
        "canal",
        "finalidade",
        "objetivo",
        "texto_base",
        "pedido_id",
        "produto_id",
        "motivo",
        "idempotency_key",
    ):
        if campo in normalizados and normalizados[campo] is not None:
            normalizados[campo] = _texto(normalizados[campo], campo)
    if tool is ToolGerenteIA.GERAR_RELATORIO and normalizados["tipo"] not in {
        "operacional",
        "financeiro_agregado",
        "sla",
    }:
        raise ErroGerenteIA("tipo_relatorio_invalido")
    if tool is ToolGerenteIA.PREPARAR_CAMPANHA:
        if len(str(normalizados["texto_base"])) > 2000:
            raise ErroGerenteIA("texto_campanha_muito_longo")
        if len(str(normalizados["objetivo"])) > 240:
            raise ErroGerenteIA("objetivo_campanha_muito_longo")
    if "motivo" in normalizados and len(str(normalizados["motivo"])) > 500:
        raise ErroGerenteIA("motivo_muito_longo")
    return normalizados


def natureza_tool(tool: ToolGerenteIA) -> NaturezaTool:
    try:
        return ESPECIFICACOES[tool].natureza
    except KeyError as exc:
        raise ErroGerenteIA("tool_nao_permitida") from exc


def _inteiro(valor: ValorPrimitivo, codigo: str) -> int:
    if isinstance(valor, bool):
        raise ErroGerenteIA(codigo)
    try:
        inteiro = int(valor)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ErroGerenteIA(codigo) from exc
    if isinstance(valor, float) and not valor.is_integer():
        raise ErroGerenteIA(codigo)
    return inteiro


def _texto(valor: ValorPrimitivo, campo: str) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ErroGerenteIA(f"{campo}_invalido")
    texto = " ".join(valor.strip().split())
    return texto
