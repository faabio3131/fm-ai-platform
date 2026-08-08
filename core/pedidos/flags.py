"""Contratos das flags futuras; defaults fail-closed preservam o legado."""

from dataclasses import dataclass


@dataclass(frozen=True)
class OrdersFeatureFlags:
    orders_shadow_write: bool = False
    orders_read_projection: bool = False
    orders_authoritative: bool = False
