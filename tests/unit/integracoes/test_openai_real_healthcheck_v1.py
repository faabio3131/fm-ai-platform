from datetime import datetime, timezone

from infra.integracoes.openai_healthcheck import (
    _classificar_falha_openai,
    _evidencia,
)


class _Contexto:
    tenant_id = "tenant-a"
    unidade_id = "unidade-a"


class _ErroHTTP(Exception):
    def __init__(self, code: int, message: str = "") -> None:
        super().__init__(f"{code} {message}")
        self.code = code


def test_evidencia_openai_e_sanitizada_e_deterministica() -> None:
    contexto = _Contexto()
    agora = datetime(2026, 10, 6, 16, 0, tzinfo=timezone.utc)

    primeira = _evidencia(
        contexto=contexto,  # type: ignore[arg-type]
        configuracao_id="ia.generativa--openai",
        model="gpt-5.6-luna",
        texto="KORDENA_OPENAI_OK",
        agora=agora,
    )
    segunda = _evidencia(
        contexto=contexto,  # type: ignore[arg-type]
        configuracao_id="ia.generativa--openai",
        model="gpt-5.6-luna",
        texto="KORDENA_OPENAI_OK",
        agora=agora,
    )

    assert primeira == segunda
    assert primeira.startswith(
        "healthcheck://openai/20261006T160000Z/gpt-5.6-luna/"
    )
    assert "KORDENA_OPENAI_OK" not in primeira
    assert "secret" not in primeira.casefold()


def test_classificacao_openai_e_sanitizada_por_status() -> None:
    assert _classificar_falha_openai(_ErroHTTP(401)) == "openai_api_key_invalida"
    assert _classificar_falha_openai(_ErroHTTP(403)) == "openai_api_key_sem_permissao"
    assert _classificar_falha_openai(_ErroHTTP(404, "model not found")) == "openai_modelo_indisponivel"
    assert _classificar_falha_openai(_ErroHTTP(429)) == "openai_quota_ou_faturamento"
    assert _classificar_falha_openai(_ErroHTTP(503)) == "openai_provedor_indisponivel"


def test_classificacao_openai_inspeciona_causa_sem_devolver_segredo() -> None:
    causa = _ErroHTTP(403, "secret-value-that-must-not-surface")
    try:
        raise ConnectionError("falha segura no gateway OpenAI") from causa
    except ConnectionError as exc:
        assert _classificar_falha_openai(exc) == "openai_api_key_sem_permissao"
