from dataclasses import dataclass
from typing import Any, cast

from infra.impressao.configuracao_sqlalchemy import ResolverDestinosImpressaoSQLAlchemy


@dataclass
class _Config:
    parametros_operacionais: dict


class _Repo:
    def obter_configuracao(self, *, tenant_id: str, unidade_id: str):
        if (tenant_id, unidade_id) != ("tenant-a", "unidade-a"):
            return None
        return _Config(
            parametros_operacionais={
                "impressao": {
                    "destinos": [
                        {
                            "provider": "raw_tcp",
                            "setor_id": "chapa",
                            "impressora_id": "tcp://10.0.0.50:9100",
                            "max_tentativas": 4,
                            "ativo": True,
                        },
                        {
                            "provider": "outro",
                            "setor_id": "bar",
                            "impressora_id": "tcp://10.0.0.51:9100",
                        },
                    ]
                }
            }
        )


def test_resolver_destinos_e_estritamente_escopado() -> None:
    resolver = object.__new__(ResolverDestinosImpressaoSQLAlchemy)
    resolver._repo = cast(Any, _Repo())

    destinos = resolver.listar(tenant_id="tenant-a", unidade_id="unidade-a")
    assert len(destinos) == 1
    assert destinos[0].tenant_id == "tenant-a"
    assert destinos[0].unidade_id == "unidade-a"
    assert destinos[0].setor_id == "chapa"
    assert destinos[0].impressora_id == "tcp://10.0.0.50:9100"
    assert destinos[0].max_tentativas == 4

    assert resolver.listar(tenant_id="tenant-b", unidade_id="unidade-a") == ()
