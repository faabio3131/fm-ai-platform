# V1 Premium Visual System

## Objetivo

Transformar a v1.0 do F&M AI FOOD em um produto com percepção visual de software premium, mantendo intacta a lógica funcional já validada.

A transformação visual deve aumentar clareza, confiança operacional, velocidade de leitura e consistência entre PDV, estoque, CRM, financeiro, Central de Pedidos, KDS, Salão e Mica I.A.

## Direção visual

- **Personalidade:** tecnologia gastronômica premium, sóbria e moderna.
- **Base:** dark mode profundo, com contraste alto e superfícies em camadas.
- **Acento principal:** laranja queimado premium, usado apenas em ações e estados de foco.
- **Tipografia:** sans-serif limpa e de leitura rápida.
- **Densidade:** informação operacional compacta, sem aparência de planilha crua.
- **Hierarquia:** títulos fortes, subtítulos curtos, indicadores destacados e ações primárias inequívocas.

## Tokens iniciais

| Token | Valor | Uso |
| --- | --- | --- |
| Background | `#090D12` | Fundo geral |
| Surface | `#111820` | Widgets, cards e regiões de apoio |
| Primary | `#9A3412` | Ações primárias, foco e seleção |
| Text | `#F5F7FA` | Texto principal |

## Regras de produto

1. Nenhuma mudança visual deve alterar regras de negócio, persistência, integrações ou contratos E2E.
2. Controles nativos devem continuar reconhecíveis e acessíveis.
3. Estados de sucesso, alerta, erro e processamento precisam permanecer semanticamente claros.
4. As áreas operacionais críticas devem priorizar leitura rápida e toque/click seguro.
5. A identidade visual será centralizada para evitar estilos divergentes entre módulos.

## Fases da transformação

### Fase 1 — Fundação visual

- Aplicar tema global próprio via `.streamlit/config.toml`.
- Definir paleta, contraste e tipografia base.
- Registrar o sistema visual da v1.0.

### Fase 2 — Shell premium

- Redesenhar sidebar corporativa.
- Criar cabeçalho executivo do produto.
- Melhorar navegação principal e percepção de produto único.
- Padronizar espaçamentos e divisores.

### Fase 3 — Componentes operacionais

- Botões primários e secundários.
- Inputs, selects, radios, checkboxes e uploaders.
- Métricas, cards, tabelas e dataframes.
- Alertas, estados vazios, loading e feedback de sucesso.
- Expander, tabs e formulários.

### Fase 4 — Telas críticas

Prioridade de refinamento visual:

1. Frente de Caixa / PDV.
2. Dashboard Financeiro.
3. Central de Pedidos.
4. KDS por Setor.
5. Mesas e Comandas.
6. Estoque e Validades.
7. Engenharia de Cardápio.
8. CRM e Cashback.
9. Mica I.A.

### Fase 5 — Polimento final

- Responsividade.
- Consistência de microcopy.
- Estados hover/focus/disabled.
- Hierarquia para telas menores.
- Revisão visual completa antes de declarar a v1.0 encerrada.

## Critério de conclusão

A v1.0 só será considerada visualmente concluída quando todas as telas parecerem partes do mesmo produto, sem áreas com aparência padrão ou provisória do framework e sem regressão funcional.
