from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from urllib.parse import quote

PIX_QR_BASE_URL = "https://api.qrserver.com/v1/create-qr-code/"
DINHEIRO_ESPECIE = "Dinheiro Em Espécie"
CLIENTE_BALCAO_ID = 0
CLIENTE_BALCAO_LABEL = "Cliente Balcão / Não Identificado"
FORMAS_PAGAMENTO_PERMITIDAS = (
    "Pix (Gerar QR Code Instantâneo)",
    "Cartão de Crédito",
    "Cartão de Débito",
    DINHEIRO_ESPECIE,
)


@dataclass(frozen=True)
class ValidacaoPDVResultado:
    valido: bool
    codigo: str | None = None
    mensagem: str | None = None
    total_bruto: Decimal = Decimal("0.00")
    desconto_cashback: Decimal = Decimal("0.00")
    total_final: Decimal = Decimal("0.00")
    valor_recebido: Decimal | None = None
    troco: Decimal | None = None
    quantidade: int | None = None
    erros_campos: dict[str, str] = field(default_factory=dict)


def moeda_decimal(valor: float | int | str | Decimal) -> Decimal:
    decimal = Decimal(str(valor))
    if not decimal.is_finite():
        raise InvalidOperation
    return decimal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def formatar_moeda_br(valor: float | int | str | Decimal) -> str:
    quantizado = moeda_decimal(valor)
    sinal = "-" if quantizado < 0 else ""
    texto = (
        f"{abs(quantizado):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )
    return f"{sinal}R$ {texto}"


def montar_payload_pix_simulado(total_final: float | int | str | Decimal) -> str:
    return f"FMFIFOOD_PIX_SIMULADO_{formatar_moeda_br(total_final)}"


def montar_linha_total_pdv(
    rotulo: str, valor: float | int | str | Decimal, *, negativo: bool = False
) -> str:
    prefixo = "-" if negativo else ""
    return f"{rotulo}: {prefixo}{formatar_moeda_br(valor)}"


def calcular_troco(
    total: float | int | str | Decimal, valor_recebido: float | int | str | Decimal
) -> Decimal:
    return (moeda_decimal(valor_recebido) - moeda_decimal(total)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def pagamento_dinheiro_suficiente(
    total: float | int | str | Decimal, valor_recebido: float | int | str | Decimal
) -> bool:
    return calcular_troco(total, valor_recebido) >= Decimal("0.00")


def valor_faltante_pagamento(
    total: float | int | str | Decimal, valor_recebido: float | int | str | Decimal
) -> Decimal:
    falta = moeda_decimal(total) - moeda_decimal(valor_recebido)
    return max(falta, Decimal("0.00"))


def deve_exibir_troco(forma_pagamento: str) -> bool:
    return forma_pagamento == DINHEIRO_ESPECIE


def deve_exibir_valor_recebido(forma_pagamento: str) -> bool:
    return forma_pagamento == DINHEIRO_ESPECIE


def montar_url_qrcode_pix(payload_pix: str, *, size: str = "180x180") -> str:
    data = quote(payload_pix, safe="")
    return f"{PIX_QR_BASE_URL}?size={quote(size, safe='x')}&data={data}"


def _invalido(
    codigo: str, mensagem: str, campo: str, **dados: Any
) -> ValidacaoPDVResultado:
    return ValidacaoPDVResultado(
        False, codigo, mensagem, erros_campos={campo: mensagem}, **dados
    )


def formatar_opcao_cliente_pdv(
    cliente_id: int | None, clientes_por_id: dict[int, Any]
) -> str:
    if cliente_id is None or cliente_id == CLIENTE_BALCAO_ID:
        return f"👤 {CLIENTE_BALCAO_LABEL}"
    cliente = clientes_por_id.get(cliente_id)
    if cliente is None:
        return f"👤 {CLIENTE_BALCAO_LABEL}"
    return f"{cliente.nome} (Cashback Disponível: {formatar_moeda_br(cliente.saldo_cashback)})"


def normalizar_cliente_id_pdv(cliente_id: Any, clientes_por_id: dict[int, Any]) -> int:
    try:
        cliente_id_normalizado = int(cliente_id)
    except (TypeError, ValueError):
        return CLIENTE_BALCAO_ID
    if cliente_id_normalizado == CLIENTE_BALCAO_ID:
        return CLIENTE_BALCAO_ID
    return (
        cliente_id_normalizado
        if cliente_id_normalizado in clientes_por_id
        else CLIENTE_BALCAO_ID
    )


def indice_cliente_pdv(cliente_id: Any, opcoes_cliente_ids: list[int]) -> int:
    try:
        cliente_id_normalizado = int(cliente_id)
    except (TypeError, ValueError):
        return 0
    try:
        return opcoes_cliente_ids.index(cliente_id_normalizado)
    except ValueError:
        return 0


def validar_finalizacao_pdv(
    *,
    produto: Any,
    quantidade: Any,
    forma_pagamento: str | None,
    valor_recebido: Any = None,
    cliente_selecionado: Any = None,
    cliente_existe: bool = True,
    usar_cashback: bool = False,
    desconto_cashback: Any = 0,
    pix_confirmado: bool = True,
    pix_producao: bool = False,
) -> ValidacaoPDVResultado:
    if produto is None:
        return _invalido(
            "produto_ausente", "Selecione um produto para finalizar a venda.", "produto"
        )
    if getattr(produto, "id", None) in (None, ""):
        return _invalido(
            "produto_sem_id", "Produto selecionado sem identificador válido.", "produto"
        )
    try:
        preco = moeda_decimal(getattr(produto, "preco_venda"))
    except (InvalidOperation, TypeError, ValueError):
        return _invalido(
            "preco_invalido", "Produto selecionado possui preço inválido.", "produto"
        )
    if preco < 0:
        return _invalido(
            "preco_negativo", "Produto selecionado possui preço negativo.", "produto"
        )

    if isinstance(quantidade, bool) or not isinstance(quantidade, int):
        return _invalido(
            "quantidade_nao_inteira",
            "Quantidade deve ser um número inteiro.",
            "quantidade",
        )
    if quantidade <= 0:
        return _invalido(
            "quantidade_invalida", "Quantidade deve ser maior que zero.", "quantidade"
        )

    if forma_pagamento not in FORMAS_PAGAMENTO_PERMITIDAS:
        return _invalido(
            "forma_pagamento_invalida",
            "Selecione uma forma de pagamento válida.",
            "forma_pagamento",
        )

    total_bruto = moeda_decimal(preco * quantidade)
    try:
        desconto = moeda_decimal(desconto_cashback if usar_cashback else 0)
    except (InvalidOperation, TypeError, ValueError):
        return _invalido(
            "cashback_invalido",
            "Desconto de cashback inválido.",
            "cashback",
            total_bruto=total_bruto,
        )
    if desconto < 0 or desconto > total_bruto:
        return _invalido(
            "cashback_maior_que_total",
            "Cashback não pode ser maior que o total da venda.",
            "cashback",
            total_bruto=total_bruto,
        )
    total_final = moeda_decimal(total_bruto - desconto)
    if total_final < 0:
        return _invalido(
            "total_negativo",
            "Total da venda não pode ser negativo.",
            "total",
            total_bruto=total_bruto,
            desconto_cashback=desconto,
        )
    if total_final == Decimal("0.00") and desconto != total_bruto:
        return _invalido(
            "total_zero_invalido",
            "Total zero só é permitido com cashback cobrindo todo o pedido.",
            "total",
            total_bruto=total_bruto,
            desconto_cashback=desconto,
        )

    if cliente_selecionado is not None and not cliente_existe:
        return _invalido(
            "cliente_invalido",
            "Cliente selecionado não foi encontrado. Remova ou selecione outro cliente.",
            "cliente",
            total_bruto=total_bruto,
            desconto_cashback=desconto,
            total_final=total_final,
        )

    recebido = None
    troco = None
    if forma_pagamento == DINHEIRO_ESPECIE:
        if valor_recebido in (None, ""):
            return _invalido(
                "dinheiro_sem_valor",
                "Informe um valor recebido válido.",
                "valor_recebido",
                total_bruto=total_bruto,
                desconto_cashback=desconto,
                total_final=total_final,
            )
        try:
            recebido = moeda_decimal(valor_recebido)
        except (InvalidOperation, TypeError, ValueError):
            return _invalido(
                "dinheiro_invalido",
                "Informe um valor recebido válido.",
                "valor_recebido",
                total_bruto=total_bruto,
                desconto_cashback=desconto,
                total_final=total_final,
            )
        if recebido < 0:
            return _invalido(
                "dinheiro_negativo",
                "Valor recebido não pode ser negativo.",
                "valor_recebido",
                total_bruto=total_bruto,
                desconto_cashback=desconto,
                total_final=total_final,
            )
        troco = calcular_troco(total_final, recebido)
        if troco < 0:
            return _invalido(
                "dinheiro_insuficiente",
                f"Pagamento insuficiente. Ainda faltam {formatar_moeda_br(abs(troco))}.",
                "valor_recebido",
                total_bruto=total_bruto,
                desconto_cashback=desconto,
                total_final=total_final,
                valor_recebido=recebido,
                troco=troco,
            )
    elif (
        forma_pagamento
        and forma_pagamento.startswith("Pix")
        and pix_producao
        and not pix_confirmado
    ):
        return _invalido(
            "pix_sem_confirmacao",
            "Pix em produção exige confirmação válida do gateway antes da baixa.",
            "forma_pagamento",
            total_bruto=total_bruto,
            desconto_cashback=desconto,
            total_final=total_final,
        )

    return ValidacaoPDVResultado(
        True,
        total_bruto=total_bruto,
        desconto_cashback=desconto,
        total_final=total_final,
        valor_recebido=recebido,
        troco=troco,
        quantidade=quantidade,
    )


def validar_estoque_suficiente(
    fichas_tecnicas: list[Any], insumos_por_id: dict[Any, Any], quantidade: int
) -> ValidacaoPDVResultado:
    for ficha in fichas_tecnicas:
        insumo = insumos_por_id.get(getattr(ficha, "insumo_id", None))
        necessario = float(getattr(ficha, "quantidade_utilizada", 0) or 0) * quantidade
        disponivel = float(getattr(insumo, "saldo_atual", 0) or 0) if insumo else 0.0
        if necessario > disponivel:
            nome = (
                getattr(insumo, "nome", "não identificado")
                if insumo
                else "não encontrado"
            )
            return _invalido(
                "estoque_insuficiente",
                f"Estoque insuficiente para o insumo {nome}. Disponível: {disponivel:g}, necessário: {necessario:g}.",
                "estoque",
            )
    return ValidacaoPDVResultado(True)


PDV_WIDGET_DEFAULTS = {
    "pdv_quantidade": 1,
    "pdv_cliente_id": CLIENTE_BALCAO_ID,
    "pdv_valor_recebido_dinheiro": 0.0,
    "pdv_forma_pagamento": FORMAS_PAGAMENTO_PERMITIDAS[0],
    "pdv_usa_cashback": False,
    "pdv_pix_confirmado": False,
    "pdv_troco": None,
}

PDV_RESET_FLAG = "pdv_reset_pendente"
PDV_FLASH_SUCESSO = "pdv_flash_sucesso"
PDV_PROCESSANDO = "pdv_processando"


def preparar_estado_inicial_pdv(session_state: Any) -> None:
    """Inicializa chaves do PDV antes da criação de widgets."""
    for chave, valor in PDV_WIDGET_DEFAULTS.items():
        session_state.setdefault(chave, valor)
    session_state.setdefault(PDV_PROCESSANDO, False)


def aplicar_reset_pendente_pdv(session_state: Any) -> bool:
    """Consome reset pendente e restaura defaults antes dos widgets."""
    if not session_state.pop(PDV_RESET_FLAG, False):
        preparar_estado_inicial_pdv(session_state)
        return False
    for chave, valor in PDV_WIDGET_DEFAULTS.items():
        session_state[chave] = valor
    session_state[PDV_PROCESSANDO] = False
    return True


def marcar_reset_pdv_apos_sucesso(session_state: Any, mensagem_sucesso: str) -> None:
    """Agenda reset para o próximo ciclo sem alterar chaves de widgets já instanciados."""
    session_state[PDV_FLASH_SUCESSO] = mensagem_sucesso
    session_state[PDV_RESET_FLAG] = True
    session_state[PDV_PROCESSANDO] = False


def consumir_flash_sucesso_pdv(session_state: Any) -> str | None:
    """Retorna a mensagem flash uma única vez."""
    return session_state.pop(PDV_FLASH_SUCESSO, None)


def montar_mensagem_sucesso_pdv(
    *,
    total_final: Any,
    forma_pagamento: str,
    valor_recebido: Any = None,
    troco: Any = None,
) -> str:
    partes = [
        f"🎉 Pagamento de {formatar_moeda_br(total_final)} processado com sucesso via {forma_pagamento}."
    ]
    if valor_recebido is not None:
        partes.append(f"Valor recebido: {formatar_moeda_br(valor_recebido)}.")
    if troco is not None:
        partes.append(f"Troco: {formatar_moeda_br(troco)}.")
    partes.append("Estoque baixado e venda gravada no sistema.")
    return " ".join(partes)
