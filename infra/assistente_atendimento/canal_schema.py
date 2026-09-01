"""Schema persistente do runtime de canal do Assistente V1.

Nenhum telefone, texto de conversa ou endereço é persistido em claro. O estado
necessário para continuidade do canal é cifrado; índices operacionais mantêm
apenas IDs canônicos e fingerprints não reversíveis.
"""

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)

metadata = MetaData()

assistente_canal_conversas_v1 = Table(
    "assistente_canal_conversas_v1",
    metadata,
    Column("tenant_id", String(64), primary_key=True),
    Column("unidade_id", String(64), primary_key=True),
    Column("canal", String(32), primary_key=True),
    Column("sender_hash", String(64), primary_key=True),
    Column("conversa_id", String(64), nullable=False),
    Column("recipient_ciphertext", Text, nullable=False),
    Column("state_ciphertext", Text, nullable=True),
    Column("estado", String(64), nullable=False),
    Column("pedido_id", String(64), nullable=True),
    Column("pagamento_id", String(64), nullable=True),
    Column("entrega_id", String(64), nullable=True),
    Column("ultimo_inbound_id", String(128), nullable=True),
    Column("ultimo_outbound_id", String(128), nullable=True),
    Column("ultimo_status_hash", String(64), nullable=True),
    Column("versao", Integer, nullable=False),
    Column("criado_em", DateTime(timezone=True), nullable=False),
    Column("atualizado_em", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "tenant_id",
        "unidade_id",
        "conversa_id",
        name="uq_assistente_canal_conversa_scope_v1",
    ),
    Index(
        "ix_assistente_canal_pedido_v1",
        "tenant_id",
        "unidade_id",
        "pedido_id",
    ),
    Index(
        "ix_assistente_canal_estado_v1",
        "tenant_id",
        "unidade_id",
        "estado",
        "atualizado_em",
    ),
)
