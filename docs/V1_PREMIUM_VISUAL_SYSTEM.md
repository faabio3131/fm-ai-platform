# V1 Premium Visual System

## Objetivo

Transformar a v1.0 do F&M AI FOOD em um produto com percepção visual de software premium, mantendo intacta a lógica funcional já validada.

A transformação visual deve aumentar clareza, confiança operacional, velocidade de leitura e consistência entre PDV, estoque, CRM, financeiro, Central de Pedidos, KDS, Salão e Mica I.A.

## Regra absoluta

A iniciativa visual da v1.0 não pode alterar lógica de negócio, persistência, integrações, cálculos, validações, contratos E2E ou comportamento dos fluxos existentes. Toda evolução deve ser justificável como apresentação, hierarquia visual, legibilidade, ergonomia ou consistência de interface.

## Direção visual

- **Personalidade:** tecnologia gastronômica premium, sóbria e moderna.
- **Base:** dark mode profundo, com contraste alto e superfícies em camadas.
- **Acento principal:** laranja premium, usado em ações, foco e seleção sem dominar a interface.
- **Tipografia:** sans-serif limpa, compacta e de leitura rápida.
- **Densidade:** informação operacional eficiente, sem aparência de planilha crua.
- **Hierarquia:** títulos fortes, subtítulos curtos, indicadores destacados e ações primárias inequívocas.
- **Estados:** sucesso, atenção, erro e informação com cores semânticas próprias e fundos discretos.

## Tokens consolidados da fundação

| Token | Valor | Uso |
| --- | --- | --- |
| Background | `#090D12` | Fundo geral |
| Surface | `#111820` | Widgets, cards e regiões de apoio |
| Surface Sidebar | `#0C1117` | Navegação lateral |
| Primary | `#F97316` | Ações primárias, foco e seleção |
| Primary Soft | `#FDBA74` | Links, detalhes e realces secundários |
| Text | `#F5F7FA` | Texto principal |
| Border | `#29313A` | Limites de componentes |
| Success | `#34D399` | Estados positivos |
| Warning | `#FBBF24` | Atenção e prevenção |
| Error | `#FB7185` | Erro e risco |
| Info | `#60A5FA` | Informação contextual |

## Regras de produto

1. Nenhuma mudança visual deve alterar regras de negócio, persistência, integrações ou contratos E2E.
2. Controles nativos devem continuar reconhecíveis e acessíveis.
3. Estados de sucesso, alerta, erro e processamento precisam permanecer semanticamente claros.
4. As áreas operacionais críticas devem priorizar leitura rápida e toque/click seguro.
5. A identidade visual será centralizada para evitar estilos divergentes entre módulos.
6. Contraste, foco e legibilidade têm prioridade sobre efeitos decorativos.
7. Nenhuma tela pode parecer pertencer a um produto diferente das demais.

## Fases da transformação

### Fase 1 — Fundação visual — EM EXECUÇÃO

- [x] Aplicar tema global próprio via `.streamlit/config.toml`.
- [x] Definir paleta e contraste.
- [x] Padronizar tipografia e hierarquia de títulos.
- [x] Padronizar bordas e arredondamentos.
- [x] Definir cores semânticas de sucesso, alerta, erro e informação.
- [x] Definir paletas categórica, sequencial e divergente para gráficos.
- [x] Criar tratamento visual próprio para sidebar.
- [x] Registrar o sistema visual da v1.0.
- [ ] Validar visualmente em execução local antes do fechamento da fase.

### Fase 2 — Shell premium

- Redesenhar visualmente a sidebar corporativa sem alterar seus dados ou estados.
- Refinar o cabeçalho executivo do produto preservando o conteúdo funcional.
- Melhorar a navegação principal sem mudar a estrutura ou destino das abas.
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
- Consistência de microcopy visual.
- Estados hover/focus/disabled.
- Hierarquia para telas menores.
- Revisão visual completa antes de declarar a v1.0 encerrada.

## Gate visual antes do merge

Antes de qualquer merge desta iniciativa deve ser confirmado:

- diff sem alteração de regras de negócio;
- nenhuma mudança em cálculos, queries, persistência ou integrações;
- mesmos controles e mesmos fluxos funcionais;
- nenhuma regressão nos gates automatizados existentes;
- revisão visual das telas afetadas;
- contraste e legibilidade adequados para operação prolongada.

## Critério de conclusão

A v1.0 só será considerada visualmente concluída quando todas as telas parecerem partes do mesmo produto, sem áreas com aparência padrão ou provisória do framework e sem regressão funcional.
