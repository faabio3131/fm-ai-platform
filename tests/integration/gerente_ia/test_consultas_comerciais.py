from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from infra.gerente_ia import ConsultasGerenciaisSQLAlchemy
from migrations.runner import run_migrations


def test_core_correlaciona_fontes_canonicas_sem_vazar_outro_tenant() -> None:
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)
    with engine.begin() as connection:
        for tenant, pedido in (("tenant-a", "pedido-a"), ("tenant-b", "pedido-b")):
            connection.execute(
                text(
                    "insert into pedidos_v1 "
                    "(id,tenant_id,unidade_id,origem,canal,status,criado_em,atualizado_em,versao,correlation_id,idempotency_key,request_hash,subtotal,descontos,taxas,total) "
                    "values (:id,:tenant,'loja-1','pdv','pdv','confirmado',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,1,:corr,:idem,:hash,100,0,0,100)"
                ),
                {"id": pedido, "tenant": tenant, "corr": f"corr-{tenant}", "idem": f"idem-{tenant}", "hash": tenant.ljust(64, "0")},
            )
        connection.execute(
            text(
                "insert into vendas_financeiras_v1 "
                "(id,tenant_id,unidade_id,pedido_id,criterio_codigo,criterio_versao,valor,moeda,metodo,reconhecida_em,correlation_id,idempotency_key,request_hash) "
                "values ('venda-a','tenant-a','loja-1','pedido-a','confirmado',1,100,'BRL','pix',CURRENT_TIMESTAMP,'corr-a','venda-idem-a',:hash)"
            ),
            {"hash": "a" * 64},
        )
        connection.execute(
            text(
                "insert into entregas_v1 "
                "(id,tenant_id,unidade_id,pedido_id,endereco_id,modalidade,status,versao,tentativa,atualizado_em) "
                "values ('entrega-a','tenant-a','loja-1','pedido-a','end-a','propria','em_rota',1,1,CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "insert into setores_producao_v1 "
                "(id,tenant_id,unidade_id,codigo,nome,ordem,ativo,criado_em,atualizado_em) "
                "values ('setor-a','tenant-a','loja-1','chapa','Chapa',1,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "insert into producao_itens_v1 "
                "(id,tenant_id,unidade_id,pedido_id,pedido_item_id,setor_id,status,prioridade,quantidade,tentativa,versao,criado_em,atualizado_em,pausa_acumulada_segundos,idempotency_key,request_hash) "
                "values ('prod-a','tenant-a','loja-1','pedido-a','item-a','setor-a','em_preparo',2,1,1,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,0,'prod-idem-a',:hash)"
            ),
            {"hash": "b" * 64},
        )
        connection.execute(
            text(
                "insert into fm_servicos_externos_config_v1 "
                "(tenant_id,unidade_id,configuracao_id,servico,provedor,conta_externa,ambiente,parametros_publicos,finalidades_credenciais,habilitada,homologada,versao,atualizado_por,correlation_id,criado_em,atualizado_em) "
                "values ('tenant-a','loja-1','maps','mapas','google_maps','billing','homologacao','{}','{}',1,1,1,'admin','corr-a',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            )
        )

    with Session(engine) as session:
        consultas = ConsultasGerenciaisSQLAlchemy(session)
        pedidos = consultas.consultar_pedidos(
            tenant_id="tenant-a", unidade_id="loja-1", filtros={}
        )
        relatorio = consultas.gerar_relatorio(
            tenant_id="tenant-a", unidade_id="loja-1", filtros={}
        )[0].para_dict()

    assert [item.para_dict()["pedido_id"] for item in pedidos] == ["pedido-a"]
    assert relatorio == {
        "entregas_abertas": 1,
        "integracoes_prontas": 1,
        "itens_cozinha": 1,
        "pedidos": 1,
        "receita_confirmada": 100.0,
    }
