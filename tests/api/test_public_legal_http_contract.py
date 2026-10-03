from fastapi import FastAPI
from fastapi.testclient import TestClient

from http_api.public_legal import build_public_legal_router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(build_public_legal_router())
    return TestClient(app)


def test_public_legal_lista_versoes_ativas() -> None:
    response = _client().get("/v1/public/legal/documents")
    assert response.status_code == 200
    documents = response.json()["documents"]
    assert {document["document_type"] for document in documents} == {
        "terms",
        "privacy",
        "dpa",
    }
    assert all(document["version"] == "1.0" for document in documents)
    assert all(len(document["sha256"]) == 64 for document in documents)


def test_public_legal_entrega_conteudo_exato_para_leitura() -> None:
    response = _client().get("/v1/public/legal/documents/terms")
    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == "1.0"
    assert payload["public_path"] == "/legal/termos"
    assert payload["content"].startswith("# TERMOS DE USO DO KORDENA")


def test_public_legal_rejeita_tipo_desconhecido() -> None:
    response = _client().get("/v1/public/legal/documents/desconhecido")
    assert response.status_code == 404
