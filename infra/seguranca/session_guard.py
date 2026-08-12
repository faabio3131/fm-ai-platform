"""Sessão ORM comercial com proteção contra persistência de segredos legados."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

_FORBIDDEN_SECRET_ATTRIBUTES = frozenset(
    {
        "meta_access_token",
        "whatsapp_token",
        "gateway_api_key",
    }
)


class SegredoLegadoEmTextoPuro(RuntimeError):
    pass


class CommercialGuardedSession(Session):
    """Recusa objetos ORM que tentem salvar credenciais em colunas legadas."""

    def flush(self, objects=None) -> None:  # type: ignore[no-untyped-def,override]
        candidates = set(self.new).union(self.dirty)
        for instance in candidates:
            for attribute in _FORBIDDEN_SECRET_ATTRIBUTES:
                if not hasattr(instance, attribute):
                    continue
                value = getattr(instance, attribute, None)
                if value is not None and str(value).strip():
                    raise SegredoLegadoEmTextoPuro(
                        f"campo legado {attribute} nao pode armazenar segredo em runtime comercial; "
                        "use uma referencia do SecretStore"
                    )
        super().flush(objects)


def build_session_factory(*, engine: Engine, commercial: bool) -> Callable[[], Session]:
    session_class = CommercialGuardedSession if commercial else Session
    factory = sessionmaker(
        bind=engine,
        class_=session_class,
        autocommit=False,
        autoflush=False,
    )
    return factory
