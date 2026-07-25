from pydantic import BaseModel
from typing import List, Optional

class TextoCozinha(BaseModel):
    texto_bruto: str

class ItemIngrediente(BaseModel):
    insumo_id: int
    quantidade_gasta: float

class ProdutoCreateIA(BaseModel):
    nome: str
    preco_venda: float
    categoria: str
    ingredientes: Optional[List[ItemIngrediente]] = []

class ProdutoResponse(BaseModel):
    id: int
    nome: str
    descricao_ai: str
    preco_venda: float
    categoria: str
    disponivel: bool
    status_estoque: str
    custo_total_cmv: float
    margem_lucro_percentual: float
    margem_exibicao: str

class InsumoCreate(BaseModel):
    nome: str
    unidade_medida: str
    custo_unitario: float
    estoque_atual: float

class BaixaEstoqueItem(BaseModel):
    insumo: str
    quantidade_utilizada: float
    estoque_restante: float
    unidade: str
    status_alerta: str

class VendaResponse(BaseModel):
    mensagem: str
    produto_vendido: str
    quantidade_vendida: int
    faturamento_bruto: float
    relatorio_estoque: List[BaixaEstoqueItem]