"""Execução agendável da projeção econômica do AI FinOps.

Executar em serviço de job isolado, fora do HTTP:
  python -m scripts.project_ai_finops_usage

Configurar agendamento efetivo somente na fase de implantação posterior à
construção. Não chama provider de IA, não cria custos e não publica preços.
"""

from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from core.runtime import build_engine, load_runtime_settings
from infra.ai_finops_projector import AIFinOpsProjector

BATCH_SIZE = 500
MAX_BATCHES = 20


def project_finops(*, batch_size: int = BATCH_SIZE, max_batches: int = MAX_BATCHES) -> int:
    if not 1 <= batch_size <= BATCH_SIZE:
        raise ValueError("finops.batch_size_invalido")
    if not 1 <= max_batches <= MAX_BATCHES:
        raise ValueError("finops.max_batches_invalido")
    engine = build_engine(load_runtime_settings())
    try:
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        projector = AIFinOpsProjector(factory)
        processed = 0
        for _ in range(max_batches):
            result = projector.project_batch(limite=batch_size)
            processed += result.processed_events
            if result.processed_events < batch_size:
                break
        return processed
    finally:
        engine.dispose()


if __name__ == "__main__":
    print(f"ai_finops_events_projected={project_finops()}")
