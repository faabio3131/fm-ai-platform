"""Feature flag do diretório canônico de notificações internas."""

import os


def internal_notifications_v1_enabled() -> bool:
    return os.getenv("FM_AI_INTERNAL_NOTIFICATIONS_V1") == "1"
