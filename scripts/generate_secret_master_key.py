"""Gera a chave mestra de infraestrutura para o cofre de integrações.

Uso:
    python -m scripts.generate_secret_master_key

O valor deve ser armazenado no ambiente seguro do servidor como
FM_AI_SECRET_MASTER_KEY. Não deve ser commitado no repositório.
"""

from cryptography.fernet import Fernet


def main() -> int:
    print(Fernet.generate_key().decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
