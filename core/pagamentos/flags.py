from dataclasses import dataclass


@dataclass(frozen=True)
class FlagsPagamentosV1:
    payments_v1_enabled: bool = False
    sales_from_orders_enabled: bool = False
    legacy_sale_adapter_enabled: bool = False
