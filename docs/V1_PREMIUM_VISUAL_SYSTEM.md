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

### Fase 1 — Fundação visual — CONCLUÍDA

- [x] Aplicar tema global próprio via `.streamlit/config.toml`.
- [x] Definir paleta e contraste.
- [x] Padronizar tipografia e hierarquia de títulos.
- [x] Padronizar bordas e arredondamentos.
- [x] Definir cores semânticas de sucesso, alerta, erro e informação.
- [x] Definir paletas categórica, sequencial e divergente para gráficos.
- [x] Criar tratamento visual próprio para sidebar.
- [x] Registrar o sistema visual da v1.0.

### Fase 2 — Shell premium — CONCLUÍDA

- [x] Refinar visualmente a sidebar corporativa sem alterar seus dados ou estados.
- [x] Refinar o cabeçalho e o shell principal do produto.
- [x] Melhorar a navegação principal sem mudar estrutura ou destino das abas.
- [x] Padronizar espaçamentos, superfícies e divisores.

### Fase 3 — Componentes operacionais — CONCLUÍDA

- [x] Botões primários e secundários.
- [x] Inputs, selects, radios, checkboxes e uploaders.
- [x] Métricas, cards, tabelas e dataframes.
- [x] Alertas, estados vazios, loading e feedback visual.
- [x] Expanders, tabs e formulários.
- [x] Foco por teclado, disabled states e redução de movimento.

### Fase 4 — Telas críticas — CONCLUÍDA VIA CAMADA GLOBAL

A camada visual centralizada cobre os componentes nativos utilizados por:

1. Frente de Caixa / PDV.
2. Dashboard Financeiro.
3. Central de Pedidos.
4. KDS por Setor.
5. Mesas e Comandas.
6. Estoque e Validades.
7. Engenharia de Cardápio.
8. CRM e Cashback.
9. Mica I.A.

Os módulos funcionais dessas áreas permanecem sem alterações de regra de negócio.

### Fase 5 — Polimento final — CONCLUÍDA

- [x] Responsividade para desktop e telas menores.
- [x] Estados hover/focus/disabled.
- [x] Hierarquia para telas menores.
- [x] Scrollbars discretas e superfícies em camadas.
- [x] Suporte a `prefers-reduced-motion`.
- [x] Revisão do diff para confirmar escopo visual.

## Arquitetura da implementação

- `.streamlit/config.toml`: tokens e tema oficial do Streamlit.
- `premium_ui.py`: camada CSS centralizada de apresentação, sem estado ou lógica de negócio.
- `app.py`: apenas importa e ativa a camada visual após `st.set_page_config`; nenhuma lógica existente foi reescrita.

## Validação final do runtime visual

Na última rodada que alterou o runtime visual:

- `app.py` recebeu somente duas linhas de ativação visual;
- nenhuma linha funcional existente foi removida;
- nenhuma query, cálculo, validação, persistência ou integração foi alterada;
- 11 dos 12 workflows concluíram com sucesso, incluindo Hardening Gate E, Salão, CRM, Mica, Delivery, Gerente IA, Marketplace, Adapters, Entrega, Garçom e Impressão;
- o workflow KDS teve sucesso no E2E específico de KDS, Ruff/mypy e testes Python, mas o E2E geral apresentou uma falha isolada no teste legado de CRM/PDV;
- o mesmo teste legado já havia falhado, no mesmo ponto de sincronização do seletor de pagamento, em execução anterior à iniciativa visual, demonstrando que a oscilação é preexistente e não foi introduzida por esta transformação;
- outro teste completo de pagamento em dinheiro passou na mesma execução.

Os commits posteriores à rodada de runtime alteram somente este documento de registro e não modificam a aplicação.

O warning legado de `use_container_width` foi deliberadamente mantido fora desta iniciativa para não ampliar o escopo além da transformação visual.

## Gate visual antes do merge

Antes do merge desta iniciativa deve ser confirmado:

- diff sem alteração de regras de negócio;
- nenhuma mudança em cálculos, queries, persistência ou integrações;
- mesmos controles e mesmos fluxos funcionais;
- ausência de regressão nova nos gates automatizados existentes;
- contraste e legibilidade adequados para operação prolongada;
- aprovação explícita do merge.

## Critério de conclusão

A transformação visual desta etapa é considerada concluída quando todas as áreas compartilham o mesmo sistema visual, os módulos funcionais permanecem intactos e não há regressão nova atribuível às mudanças de apresentação.
