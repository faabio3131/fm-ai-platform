"""Identificadores persistiveis e matriz inicial (nao decisao final)."""

from enum import StrEnum


class Permissao(StrEnum):
    PEDIDO_CRIAR = "pedido.criar"
    PEDIDO_VISUALIZAR = "pedido.visualizar"
    PEDIDO_ALTERAR = "pedido.alterar"
    PEDIDO_CANCELAR = "pedido.cancelar"
    PEDIDO_PRIORIZAR = "pedido.priorizar"
    PEDIDO_LIBERAR_COZINHA = "pedido.liberar_cozinha"
    PDV_OPERAR = "pdv.operar"
    PAGAMENTO_REGISTRAR = "pagamento.registrar"
    PAGAMENTO_CONFIRMAR = "pagamento.confirmar"
    PAGAMENTO_ESTORNAR = "pagamento.estornar"
    DESCONTO_APLICAR = "desconto.aplicar"
    DESCONTO_ACIMA_LIMITE = "desconto.acima_limite"
    CAIXA_ABRIR = "caixa.abrir"
    CAIXA_FECHAR = "caixa.fechar"
    FINANCEIRO_VISUALIZAR = "financeiro.visualizar"
    ESTOQUE_VISUALIZAR = "estoque.visualizar"
    ESTOQUE_AJUSTAR = "estoque.ajustar"
    ESTOQUE_BAIXAR = "estoque.baixar"
    ESTOQUE_LIBERAR = "estoque.liberar"
    COMPRA_APROVAR = "compra.aprovar"
    PRODUCAO_VISUALIZAR = "producao.visualizar"
    PRODUCAO_ACEITAR = "producao.aceitar"
    PRODUCAO_ATUALIZAR = "producao.atualizar"
    EXPEDICAO_OPERAR = "expedicao.operar"
    MESA_ABRIR = "mesa.abrir"
    MESA_TRANSFERIR = "mesa.transferir"
    COMANDA_ALTERAR = "comanda.alterar"
    COMANDA_FECHAR = "comanda.fechar"
    CLIENTE_VISUALIZAR = "cliente.visualizar"
    CLIENTE_EDITAR = "cliente.editar"
    CAMPANHA_CRIAR = "campanha.criar"
    CAMPANHA_APROVAR = "campanha.aprovar"
    CONSENTIMENTO_VISUALIZAR = "consentimento.visualizar"
    USUARIO_GERENCIAR = "usuario.gerenciar"
    PERMISSAO_GERENCIAR = "permissao.gerenciar"
    INTEGRACAO_GERENCIAR = "integracao.gerenciar"
    AUDITORIA_VISUALIZAR = "auditoria.visualizar"
    CONFIGURACAO_ALTERAR = "configuracao.alterar"
    GERENTE_IA_CONSULTAR = "gerente_ia.consultar"
    GERENTE_IA_PREPARAR_ACAO = "gerente_ia.preparar_acao"
    GERENTE_IA_EXECUTAR_ACAO = "gerente_ia.executar_acao"
    GERENTE_IA_APROVAR_CAMPANHA = "gerente_ia.aprovar_campanha"


class Papel(StrEnum):
    ADMINISTRADOR = "administrador"
    GERENTE = "gerente"
    CAIXA = "caixa"
    GARCOM = "garcom"
    COZINHA = "cozinha"
    EXPEDICAO = "expedicao"
    ENTREGADOR = "entregador"
    ATENDIMENTO = "atendimento"
    FINANCEIRO = "financeiro"
    GERENTE_IA = "gerente_ia"


MATRIZ_PADRAO: dict[Papel, frozenset[Permissao]] = {
    Papel.ADMINISTRADOR: frozenset(Permissao),
    Papel.GERENTE: frozenset(
        p for p in Permissao if not p.value.startswith("permissao.")
    ),
    Papel.CAIXA: frozenset(
        {
            Permissao.PDV_OPERAR,
            Permissao.PAGAMENTO_REGISTRAR,
            Permissao.PAGAMENTO_CONFIRMAR,
            Permissao.PAGAMENTO_ESTORNAR,
            Permissao.DESCONTO_APLICAR,
            Permissao.CAIXA_ABRIR,
            Permissao.CAIXA_FECHAR,
        }
    ),
    Papel.GARCOM: frozenset(
        {
            Permissao.PEDIDO_CRIAR,
            Permissao.PEDIDO_VISUALIZAR,
            Permissao.PEDIDO_ALTERAR,
            Permissao.MESA_ABRIR,
            Permissao.COMANDA_ALTERAR,
        }
    ),
    Papel.COZINHA: frozenset(
        {
            Permissao.PRODUCAO_VISUALIZAR,
            Permissao.PRODUCAO_ACEITAR,
            Permissao.PRODUCAO_ATUALIZAR,
        }
    ),
    Papel.EXPEDICAO: frozenset(
        {Permissao.PRODUCAO_VISUALIZAR, Permissao.EXPEDICAO_OPERAR}
    ),
    Papel.ENTREGADOR: frozenset({Permissao.EXPEDICAO_OPERAR}),
    Papel.ATENDIMENTO: frozenset(
        {
            Permissao.PEDIDO_CRIAR,
            Permissao.PEDIDO_VISUALIZAR,
            Permissao.CLIENTE_VISUALIZAR,
        }
    ),
    Papel.FINANCEIRO: frozenset(
        {
            Permissao.FINANCEIRO_VISUALIZAR,
            Permissao.PAGAMENTO_CONFIRMAR,
            Permissao.PAGAMENTO_ESTORNAR,
        }
    ),
    Papel.GERENTE_IA: frozenset(
        {
            Permissao.PEDIDO_VISUALIZAR,
            Permissao.GERENTE_IA_CONSULTAR,
            Permissao.GERENTE_IA_PREPARAR_ACAO,
        }
    ),
}
