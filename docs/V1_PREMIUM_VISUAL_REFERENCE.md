# V1 — Referência Canônica para Transformação Visual Premium Final

**Status atual:** REFERÊNCIA PRESERVADA — implementação visual antiga NÃO deve ser mergeada na `main` atual.  
**Origem:** PR histórica #47 (`agent/v1-premium-visual-foundation`).  
**Regra:** a transformação visual completa só deve ocorrer depois do fechamento funcional da V1 e deve ser reconstruída sobre a `main` vigente, sem reaproveitamento cego de código antigo.

## 1. Objetivo

Transformar a V1 em um produto com percepção visual de software premium, com aparência de plataforma madura, consistente e de alto padrão, preservando integralmente a lógica funcional já validada.

A transformação deve melhorar clareza, confiança operacional, velocidade de leitura, ergonomia e consistência entre PDV, Estoque, CRM, Financeiro, Central de Pedidos, KDS, Salão, Expedição/Entrega, Administração e Assistente/Gerente IA.

## 2. Regra absoluta

A camada visual não pode alterar:

- regras de negócio;
- persistência;
- integrações;
- cálculos;
- validações;
- contratos transacionais;
- RBAC/tenant isolation;
- contratos E2E;
- autoridade dos domínios.

Toda mudança deve ser justificável como apresentação, hierarquia visual, legibilidade, acessibilidade, ergonomia ou consistência de interface.

## 3. Direção visual preservada

- personalidade: tecnologia gastronômica premium, sóbria e moderna;
- base: dark mode profundo, superfícies em camadas e contraste alto;
- acento principal: laranja premium usado com disciplina;
- tipografia: sans-serif limpa, compacta e de leitura rápida;
- densidade: informação operacional eficiente, sem aparência de planilha crua;
- hierarquia: títulos fortes, indicadores claros e ações primárias inequívocas;
- estados: sucesso, atenção, erro e informação semanticamente distintos;
- navegação e módulos devem parecer parte de um único produto.

### Tokens históricos de referência

| Token | Valor histórico | Uso |
| --- | --- | --- |
| Background | `#090D12` | Fundo geral |
| Surface | `#111820` | Cards e superfícies |
| Surface Sidebar | `#0C1117` | Navegação lateral |
| Primary | `#F97316` | Ações primárias |
| Primary Soft | `#FDBA74` | Realces secundários |
| Text | `#F5F7FA` | Texto principal |
| Border | `#29313A` | Limites de componentes |
| Success | `#34D399` | Sucesso |
| Warning | `#FBBF24` | Atenção |
| Error | `#FB7185` | Erro |
| Info | `#60A5FA` | Informação |

Esses tokens são direção de produto, não obrigação técnica. A implementação final deve ser revisada contra a aplicação atual.

## 4. Critérios da reconstrução final

A fase visual final deverá:

1. partir da `main` funcionalmente fechada;
2. fazer inventário de todas as superfícies atuais antes de editar;
3. centralizar tokens e estilos para evitar divergência entre módulos;
4. preservar controles reconhecíveis e acessíveis;
5. garantir foco por teclado, contraste, estados disabled e redução de movimento;
6. ser responsiva em desktop, tablet e celular onde cada operação exigir;
7. manter áreas críticas rápidas para leitura e toque/click seguro;
8. executar toda a matriz de regressão funcional antes do merge;
9. provar por diff/revisão que não houve mudança de domínio ou autoridade;
10. receber aprovação humana explícita antes do merge.

## 5. Tratamento da implementação histórica

Os arquivos históricos `.streamlit/config.toml`, `premium_ui.py` e as duas linhas de ativação em `app.py` da PR #47 servem apenas como referência de estudo.

A branch histórica ficou centenas de commits atrás da linha atual. Portanto:

- não deve ser mergeada diretamente;
- não deve ser rebaseada automaticamente para produção;
- não deve sobrescrever UI, navegação ou contratos atuais;
- qualquer ideia útil deve ser reimplementada de forma seletiva sobre a arquitetura vigente.

## 6. Sequência obrigatória

A transformação visual premium final permanece posterior ao fechamento funcional da V1, incluindo os requisitos funcionais ainda pendentes e as pendências finais explicitamente aceitas.

O fechamento de PRs visuais antigas durante a faxina canônica não elimina este requisito. Esta referência existe justamente para preservar a intenção de produto sem manter uma branch antiga como falsa candidata de merge.