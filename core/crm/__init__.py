"""CRM e conversão consentida V1 — PR19."""

from .erros import ErroCRM
from .flags import crm_v1_enabled
from .modelos import (
    BaseLegalMarketing,
    BeneficioCRM,
    CanalMarketing,
    ClienteCRM,
    ClienteMarketplaceRestrito,
    ConsentimentoMarketing,
    ContatoCRM,
    EtapaFunilCRM,
    EventoFunilCRM,
    FinalidadeMarketing,
    OrigemClienteCRM,
    ResultadoConversaoCRM,
    ResultadoDespachoMarketing,
    ResumoFunilCRM,
    StatusConsentimento,
    TipoBeneficioCRM,
)
from .servicos import ServicoCRM

__all__ = [
    "BaseLegalMarketing",
    "BeneficioCRM",
    "CanalMarketing",
    "ClienteCRM",
    "ClienteMarketplaceRestrito",
    "ConsentimentoMarketing",
    "ContatoCRM",
    "ErroCRM",
    "EtapaFunilCRM",
    "EventoFunilCRM",
    "FinalidadeMarketing",
    "OrigemClienteCRM",
    "ResultadoConversaoCRM",
    "ResultadoDespachoMarketing",
    "ResumoFunilCRM",
    "ServicoCRM",
    "StatusConsentimento",
    "TipoBeneficioCRM",
    "crm_v1_enabled",
]
