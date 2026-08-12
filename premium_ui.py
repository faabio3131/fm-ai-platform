"""Camada exclusivamente visual da v1.0.

Este modulo injeta apenas CSS de apresentacao sobre componentes Streamlit ja
existentes. Nao altera estado, regras de negocio, validacoes, persistencia,
integracoes, callbacks ou fluxos funcionais.
"""

import streamlit as st


_PREMIUM_CSS = r"""
<style>
:root {
  --fm-bg: #090d12;
  --fm-surface: #111820;
  --fm-surface-2: #151d26;
  --fm-surface-3: #19232e;
  --fm-border: #29313a;
  --fm-border-soft: rgba(148, 163, 184, 0.16);
  --fm-text: #f5f7fa;
  --fm-muted: #9aa8b7;
  --fm-primary: #f97316;
  --fm-primary-2: #fb923c;
  --fm-primary-soft: rgba(249, 115, 22, 0.12);
  --fm-success: #34d399;
  --fm-warning: #fbbf24;
  --fm-error: #fb7185;
  --fm-info: #60a5fa;
  --fm-shadow: 0 18px 50px rgba(0, 0, 0, 0.26);
  --fm-shadow-soft: 0 8px 28px rgba(0, 0, 0, 0.18);
}

html, body, [class*="css"] {
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

/* Shell principal */
[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(circle at 78% -10%, rgba(249, 115, 22, 0.07), transparent 34%),
    radial-gradient(circle at 18% 8%, rgba(96, 165, 250, 0.035), transparent 28%),
    var(--fm-bg);
}

[data-testid="stHeader"] {
  background: rgba(9, 13, 18, 0.76);
  backdrop-filter: blur(14px);
  border-bottom: 1px solid rgba(148, 163, 184, 0.08);
}

.block-container {
  max-width: 1680px;
  padding-top: 2.2rem;
  padding-bottom: 4rem;
}

footer { visibility: hidden; }

/* Tipografia e hierarquia */
h1, h2, h3, h4, h5, h6 {
  letter-spacing: -0.025em;
  color: var(--fm-text);
}

h1 {
  margin-bottom: 0.35rem !important;
  line-height: 1.05 !important;
}

h2, h3 {
  margin-top: 0.55rem !important;
}

p, li, label, .stCaption {
  line-height: 1.55;
}

[data-testid="stCaptionContainer"],
small {
  color: var(--fm-muted) !important;
}

a {
  text-underline-offset: 0.2rem;
}

hr {
  border: 0 !important;
  height: 1px !important;
  background: linear-gradient(90deg, transparent, rgba(148,163,184,.24), transparent) !important;
  margin: 1.45rem 0 !important;
}

/* Sidebar corporativa */
[data-testid="stSidebar"] {
  background:
    linear-gradient(180deg, rgba(249,115,22,.035), transparent 24%),
    #0c1117;
  border-right: 1px solid #25303a;
  box-shadow: 14px 0 45px rgba(0, 0, 0, 0.18);
}

[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
  padding-top: 1.25rem;
}

[data-testid="stSidebar"] img {
  border-radius: 1rem;
  filter: drop-shadow(0 14px 30px rgba(0,0,0,.26));
}

[data-testid="stSidebar"] h1 {
  font-size: 1.62rem !important;
  margin-top: .75rem !important;
}

[data-testid="stSidebar"] [data-testid="stAlert"] {
  box-shadow: none;
}

/* Navegacao por abas */
.stTabs [data-baseweb="tab-list"] {
  gap: .35rem;
  padding: .34rem;
  border: 1px solid var(--fm-border-soft);
  border-radius: 1rem;
  background: rgba(17, 24, 32, 0.72);
  box-shadow: var(--fm-shadow-soft);
  overflow-x: auto;
  scrollbar-width: thin;
}

.stTabs [data-baseweb="tab"] {
  min-height: 2.9rem;
  padding: .62rem .95rem;
  border-radius: .72rem;
  color: #aeb9c5;
  font-weight: 650;
  transition: background .16s ease, color .16s ease, transform .16s ease;
}

.stTabs [data-baseweb="tab"]:hover {
  color: var(--fm-text);
  background: rgba(255,255,255,.035);
}

.stTabs [aria-selected="true"] {
  color: #fff !important;
  background: linear-gradient(135deg, rgba(249,115,22,.22), rgba(249,115,22,.10)) !important;
  box-shadow: inset 0 0 0 1px rgba(251,146,60,.35), 0 8px 20px rgba(0,0,0,.16);
}

.stTabs [data-baseweb="tab-highlight"] {
  background-color: var(--fm-primary) !important;
  height: 2px !important;
}

/* Botoes */
.stButton > button,
.stFormSubmitButton > button,
[data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-secondary"] {
  min-height: 2.75rem;
  border-radius: .75rem !important;
  border: 1px solid rgba(148,163,184,.22) !important;
  font-weight: 700 !important;
  letter-spacing: -.01em;
  box-shadow: 0 8px 18px rgba(0,0,0,.16);
  transition: transform .14s ease, box-shadow .14s ease, border-color .14s ease, filter .14s ease;
}

.stButton > button:hover,
.stFormSubmitButton > button:hover {
  transform: translateY(-1px);
  box-shadow: 0 12px 25px rgba(0,0,0,.24);
  border-color: rgba(251,146,60,.62) !important;
}

.stButton > button:active,
.stFormSubmitButton > button:active {
  transform: translateY(0);
}

button[kind="primary"],
[data-testid="stBaseButton-primary"] {
  background: linear-gradient(135deg, #fb923c 0%, #f97316 54%, #ea580c 100%) !important;
  color: #fff !important;
  border-color: rgba(251,146,60,.55) !important;
  box-shadow: 0 10px 24px rgba(234, 88, 12, .20) !important;
}

button:disabled {
  opacity: .52 !important;
  transform: none !important;
  box-shadow: none !important;
}

/* Campos e controles */
[data-baseweb="input"] > div,
[data-baseweb="select"] > div,
[data-baseweb="base-input"],
.stTextArea textarea,
.stNumberInput input,
.stTextInput input,
.stDateInput input,
[data-testid="stFileUploaderDropzone"] {
  background: rgba(17, 24, 32, .82) !important;
  border-color: rgba(148,163,184,.24) !important;
  border-radius: .75rem !important;
  transition: border-color .14s ease, box-shadow .14s ease, background .14s ease;
}

[data-baseweb="input"] > div:focus-within,
[data-baseweb="select"] > div:focus-within,
.stTextArea textarea:focus,
.stNumberInput input:focus,
.stTextInput input:focus,
.stDateInput input:focus {
  border-color: rgba(249,115,22,.72) !important;
  box-shadow: 0 0 0 3px rgba(249,115,22,.12) !important;
  background: #131b24 !important;
}

[data-testid="stFileUploaderDropzone"] {
  border-style: dashed !important;
  padding: 1rem !important;
}

[data-testid="stFileUploaderDropzone"]:hover {
  border-color: rgba(249,115,22,.58) !important;
  background: rgba(249,115,22,.045) !important;
}

[data-baseweb="radio"] label,
[data-baseweb="checkbox"] label {
  border-radius: .55rem;
}

/* Cards, forms, containers e expanders */
[data-testid="stForm"],
[data-testid="stVerticalBlockBorderWrapper"] {
  border-color: var(--fm-border-soft) !important;
  border-radius: 1rem !important;
  background: linear-gradient(180deg, rgba(21,29,38,.76), rgba(17,24,32,.66));
  box-shadow: var(--fm-shadow-soft);
}

details {
  border: 1px solid var(--fm-border-soft) !important;
  border-radius: .9rem !important;
  background: rgba(17,24,32,.72) !important;
  overflow: hidden;
}

details summary {
  padding-top: .25rem;
  padding-bottom: .25rem;
  font-weight: 650;
}

details[open] {
  border-color: rgba(249,115,22,.22) !important;
}

/* Metricas */
[data-testid="stMetric"] {
  min-height: 7.1rem;
  padding: 1rem 1.05rem;
  border: 1px solid var(--fm-border-soft);
  border-radius: 1rem;
  background:
    linear-gradient(150deg, rgba(249,115,22,.055), transparent 48%),
    rgba(17,24,32,.82);
  box-shadow: var(--fm-shadow-soft);
}

[data-testid="stMetricLabel"] {
  color: #aab6c2 !important;
  font-weight: 650;
}

[data-testid="stMetricValue"] {
  color: #fff !important;
  letter-spacing: -.035em;
}

[data-testid="stMetricDelta"] {
  font-weight: 650;
}

/* Tabelas e dataframes */
[data-testid="stDataFrame"],
[data-testid="stTable"] {
  border: 1px solid var(--fm-border-soft);
  border-radius: 1rem;
  overflow: hidden;
  box-shadow: var(--fm-shadow-soft);
  background: rgba(17,24,32,.74);
}

[data-testid="stDataFrame"] canvas {
  border-radius: .8rem;
}

/* Alertas e feedback */
[data-testid="stAlert"] {
  border-radius: .85rem !important;
  border-width: 1px !important;
  box-shadow: 0 8px 22px rgba(0,0,0,.14);
}

[data-testid="stNotification"] {
  border-radius: .85rem !important;
  box-shadow: var(--fm-shadow-soft);
}

/* Codigo e JSON */
pre, code {
  border-radius: .65rem !important;
}

[data-testid="stJson"] {
  border: 1px solid var(--fm-border-soft);
  border-radius: .85rem;
  overflow: hidden;
}

/* Imagens */
[data-testid="stImage"] img {
  border-radius: .85rem;
}

/* Scrollbars discretas */
* {
  scrollbar-color: #374351 transparent;
  scrollbar-width: thin;
}

*::-webkit-scrollbar { width: 8px; height: 8px; }
*::-webkit-scrollbar-track { background: transparent; }
*::-webkit-scrollbar-thumb {
  background: #374351;
  border-radius: 999px;
  border: 2px solid transparent;
  background-clip: padding-box;
}
*::-webkit-scrollbar-thumb:hover { background: #4a5968; background-clip: padding-box; }

/* Foco acessivel */
button:focus-visible,
input:focus-visible,
textarea:focus-visible,
[role="tab"]:focus-visible,
[role="combobox"]:focus-visible {
  outline: 2px solid var(--fm-primary-2) !important;
  outline-offset: 2px !important;
}

/* Responsividade */
@media (max-width: 900px) {
  .block-container {
    padding-left: 1rem;
    padding-right: 1rem;
    padding-top: 1.45rem;
  }
  [data-testid="stMetric"] { min-height: 6.4rem; }
  .stTabs [data-baseweb="tab"] {
    padding: .55rem .72rem;
    white-space: nowrap;
  }
}

@media (max-width: 640px) {
  .block-container {
    padding-left: .75rem;
    padding-right: .75rem;
  }
  h1 { font-size: 1.9rem !important; }
  h2 { font-size: 1.45rem !important; }
  h3 { font-size: 1.2rem !important; }
  .stButton > button,
  .stFormSubmitButton > button { min-height: 3rem; }
  [data-testid="stMetric"] {
    min-height: auto;
    padding: .85rem .9rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    transition-duration: .001ms !important;
    animation-duration: .001ms !important;
    animation-iteration-count: 1 !important;
  }
}
</style>
"""


def apply_premium_visual_system() -> None:
    """Aplica somente a camada CSS premium da v1.0."""

    st.markdown(_PREMIUM_CSS, unsafe_allow_html=True)
