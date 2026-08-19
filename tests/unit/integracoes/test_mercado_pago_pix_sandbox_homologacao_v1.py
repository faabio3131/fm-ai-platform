from datetime import datetime, timezone

import pytest

from core.integracoes.modelos import AmbienteIntegracao, ErroConfiguracaoServico
from scripts.mercado_pago_pix_sandbox_homologacao import _evidencia, executar_teste_pix_sandbox


class _Resp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _HTTP:
    def __init__(self, criado, consultado):
        self.criado = criado
        self.consultado = consultado
        self.posts = []
        self.gets = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return _Resp(201, self.criado)

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        return _Resp(200, self.consultado)


class _Config:
    habilitada = True
    ambiente = AmbienteIntegracao.SANDBOX
    servico = "pagamentos.pix"
    provedor = "mercado_pago"
    credenciais = {"access_token": "pagamentos_pix_access_token"}


class _Repo:
    def __init__(self, session):
        pass

    def obter(self, **kwargs):
        return _Config()


class _StoreResolved:
    def reveal(self):
        return "APP_USR-test-token"


class _Store:
    def __init__(self, session):
        pass

    def resolve(self, referencia):
        return _StoreResolved()


class _ScalarRow:
    referencia = "vault-ref"


class _Session:
    def scalar(self, stmt):
        return _ScalarRow()


def _order(status="action_required"):
    return {
        "id": "ORD01SANDBOX",
        "status": status,
        "transactions": {
            "payments": [
                {
                    "payment_method": {
                        "id": "pix",
                        "type": "bank_transfer",
                        "qr_code": "000201-test",
                        "ticket_url": "https://example.invalid/ticket",
                    }
                }
            ]
        },
    }


def test_evidencia_sandbox_e_sanitizada() -> None:
    evidencia = _evidencia(
        tenant_id="tenant-a",
        unidade_id="unidade-a",
        order_id="ORD01SANDBOX",
        status="action_required",
        agora=datetime(2026, 8, 19, 22, 0, tzinfo=timezone.utc),
    )
    assert evidencia.startswith("healthcheck://mercado-pago-pix-sandbox/20260819T220000Z/")
    assert "APP_USR" not in evidencia
    assert "qr_code" not in evidencia


def test_probe_usa_payload_oficial_pix_e_nao_expoe_segredos(monkeypatch) -> None:
    import scripts.mercado_pago_pix_sandbox_homologacao as modulo

    monkeypatch.setattr(modulo, "RepositorioConfiguracoesExternasSQLAlchemy", _Repo)
    monkeypatch.setattr(modulo, "EncryptedSQLAlchemySecretStore", _Store)
    http = _HTTP(_order(), _order(status="processed"))

    resultado = executar_teste_pix_sandbox(
        session=_Session(),
        tenant_id="tenant-a",
        unidade_id="unidade-a",
        http=http,
        agora=datetime(2026, 8, 19, 22, 0, tzinfo=timezone.utc),
    )

    url, kwargs = http.posts[0]
    assert url.endswith("/v1/orders")
    assert kwargs["json"]["total_amount"] == "50.00"
    assert kwargs["json"]["payer"]["email"] == "test_user_br@testuser.com"
    assert kwargs["json"]["payer"]["first_name"] == "APRO"
    assert kwargs["json"]["transactions"]["payments"][0]["payment_method"] == {
        "id": "pix",
        "type": "bank_transfer",
    }
    assert kwargs["headers"]["Authorization"].startswith("Bearer APP_USR")
    assert resultado.order_id == "ORD01SANDBOX"
    assert resultado.qr_code_presente is True
    assert resultado.status_consulta == "processed"
    assert resultado.evidencia_ref.startswith("healthcheck://mercado-pago-pix-sandbox/")


def test_probe_bloqueia_fora_de_sandbox(monkeypatch) -> None:
    import scripts.mercado_pago_pix_sandbox_homologacao as modulo

    class _ConfigProd(_Config):
        ambiente = AmbienteIntegracao.PRODUCAO

    class _RepoProd(_Repo):
        def obter(self, **kwargs):
            return _ConfigProd()

    monkeypatch.setattr(modulo, "RepositorioConfiguracoesExternasSQLAlchemy", _RepoProd)
    with pytest.raises(ErroConfiguracaoServico, match="teste_pix_sandbox_bloqueado_fora_de_sandbox"):
        executar_teste_pix_sandbox(
            session=_Session(),
            tenant_id="tenant-a",
            unidade_id="unidade-a",
            http=_HTTP(_order(), _order()),
        )
