from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import quote

PIX_QR_BASE_URL = "https://api.qrserver.com/v1/create-qr-code/"
DINHEIRO_ESPECIE = "Dinheiro Em Espécie"


def moeda_decimal(valor: float | int | str | Decimal) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calcular_troco(total: float | int | str | Decimal, valor_recebido: float | int | str | Decimal) -> Decimal:
    return (moeda_decimal(valor_recebido) - moeda_decimal(total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def pagamento_dinheiro_suficiente(total: float | int | str | Decimal, valor_recebido: float | int | str | Decimal) -> bool:
    return calcular_troco(total, valor_recebido) >= Decimal("0.00")


def valor_faltante_pagamento(total: float | int | str | Decimal, valor_recebido: float | int | str | Decimal) -> Decimal:
    falta = moeda_decimal(total) - moeda_decimal(valor_recebido)
    return max(falta, Decimal("0.00"))


def deve_exibir_troco(forma_pagamento: str) -> bool:
    return forma_pagamento == DINHEIRO_ESPECIE


def montar_url_qrcode_pix(payload_pix: str, *, size: str = "180x180") -> str:
    data = quote(payload_pix, safe="")
    return f"{PIX_QR_BASE_URL}?size={quote(size, safe='x')}&data={data}"
