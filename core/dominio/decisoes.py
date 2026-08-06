from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .enums import CodigoDecisaoCozinha, PapelUsuario, RiscoPedido
from .erros import ErroValidacaoDominio
from .serializacao import Serializavel
from .tempo import em_utc


@dataclass(frozen=True, kw_only=True)
class DecisaoCozinha(Serializavel):
    permitido: bool
    codigo_decisao: CodigoDecisaoCozinha
    justificativa: str
    confirmacao_exigida: bool
    risco: RiscoPedido
    politica_aplicada: str
    versao_politica: str
    decidido_em: datetime
    papel_responsavel_exigido: PapelUsuario | None = None
    metadados: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "decidido_em", em_utc(self.decidido_em))
        prefixo_permitido = self.codigo_decisao.value.startswith("permitido_")
        if self.permitido != prefixo_permitido:
            raise ErroValidacaoDominio("Código de decisão incoerente com permitido")
        if not self.justificativa.strip() or not self.politica_aplicada.strip():
            raise ErroValidacaoDominio("Justificativa e política são obrigatórias")
