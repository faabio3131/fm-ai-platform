from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from application.delivery_maps_comercial import RotaDeliveryGoogleMaps
from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.permissoes import Papel
from http_api.frontend_app import build_frontend_http_app
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

SESSION_SECRET = "delivery-maps-http-secret-0123456789-abcdef"
SENHA = "Senha-Segura-Delivery-Maps-123"
TENANT = "tenant-delivery-maps-http"
UNIDADE = "unidade-delivery-maps-http"
GERENTE_EMAIL = "gerente-delivery-maps@example.com"


def _infra(monkeypatch, *, delivery_maps_resolver=None) -> TestClient:
    monkeypatch.setenv("FM_AI_SESSION_SECRET", SESSION_SECRET)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory() as session:
        RepositorioIdentidadesSQLAlchemy(session).criar_usuario(
            usuario_id="usuario-delivery-maps-gerente",
            email=GERENTE_EMAIL,
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE,
            papeis=(Papel.GERENTE,),
            unidades_permitidas=(UNIDADE,),
        )
        session.commit()

    app = build_frontend_http_app(
        settings=RuntimeSettings(
            environment=RuntimeEnvironment.TEST,
            database_url="sqlite://",
            tenant_id=TENANT,
            unidade_id=UNIDADE,
        ),
        engine=engine,
        session_factory=factory,
        delivery_maps_resolver=delivery_maps_resolver,
    )
    return TestClient(app)


def _login(client: TestClient) -> None:
    response = client.post(
        "/v1/auth/login",
        json={"email": GERENTE_EMAIL, "senha": SENHA},
    )
    assert response.status_code == 200


def test_delivery_maps_route_requires_authenticated_identity(monkeypatch) -> None:
    client = _infra(monkeypatch)

    response = client.get("/v1/delivery/clientes/cliente-1/rota")

    assert response.status_code == 401
    assert response.json() == {"erro": "credenciais_invalidas"}


def test_delivery_maps_route_uses_signed_scope_without_exposing_keys(monkeypatch) -> None:
    observed: dict[str, str] = {}

    def fake_route(
        *,
        identidade: IdentidadeUsuario,
        cliente_id: str,
        session: Session,
    ) -> RotaDeliveryGoogleMaps:
        del session
        observed["tenant"] = identidade.tenant_id
        observed["unidade"] = identidade.unidade_id
        observed["cliente"] = cliente_id
        return RotaDeliveryGoogleMaps(
            cliente_id=cliente_id,
            provedor="google_maps",
            origem_endereco="Avenida Paulista, 1578 - Sao Paulo/SP",
            destino_endereco="Praca da Se - Sao Paulo/SP",
            distancia_metros=4100,
            distancia_km=4.1,
            eta_minutos=18,
            polyline_codificada="polyline-sanitizada",
            origem_latitude=-23.5614,
            origem_longitude=-46.6559,
            destino_latitude=-23.5505,
            destino_longitude=-46.6333,
            origem_versao=3,
            endereco_ref="address://cliente-1",
        )

    client = _infra(monkeypatch, delivery_maps_resolver=fake_route)
    _login(client)

    response = client.get(
        "/v1/delivery/clientes/cliente-1/rota",
        headers={
            "X-Tenant-ID": "tenant-spoof",
            "X-Unit-ID": "unidade-spoof",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provedor"] == "google_maps"
    assert payload["distancia_metros"] == 4100
    assert payload["eta_minutos"] == 18
    assert payload["origem"]["versao"] == 3
    assert payload["destino"]["endereco_ref"] == "address://cliente-1"
    assert observed == {
        "tenant": TENANT,
        "unidade": UNIDADE,
        "cliente": "cliente-1",
    }
    serialized = str(payload).casefold()
    assert "api_key" not in serialized
    assert "server_api_key" not in serialized
    assert "browser_api_key" not in serialized
