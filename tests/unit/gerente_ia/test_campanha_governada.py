from __future__ import annotations

import pytest

from core.gerente_ia.erros import ErroGerenteIA
from core.gerente_ia.modelos import CampanhaRef


def test_campanha_ref_e_tipada_versionada_e_nao_aceita_texto_arbitrario() -> None:
    ref = CampanhaRef.de_publicacao(
        campanha_id="camp-1",
        fingerprint="a" * 64,
    )

    assert str(ref) == f"campanha://v1/camp-1/{'a' * 64}"

    with pytest.raises(ErroGerenteIA, match="campanha_ref_invalida"):
        CampanhaRef("camp-1")
