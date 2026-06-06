"""Camada visual da interface (Direção C — "Clima do dia").

Recria, dentro do Streamlit, o wireframe desenhado no Claude Design: estética
"sketch" (fundo papel, bordas irregulares, fonte manuscrita Patrick Hand),
azul-clima como destaque, semáforo de cor nos vereditos (verde/âmbar/vermelho),
emojis mantidos e tema claro + escuro.

Tudo aqui é apresentação: as funções `bloco_*` recebem os dados já calculados
(`Previsao`, `Veredito`) e devolvem **strings HTML** para `st.markdown(..., unsafe_allow_html=True)`.
Nenhum cálculo de regra acontece neste módulo.
"""

from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from rules_service import Veredito
from weather_service import Previsao

# --------------------------------------------------------------------------- #
# Temas (variáveis copiadas do wireframe: :root e [data-theme="dark"])
# --------------------------------------------------------------------------- #

TEMA_CLARO = """
  --paper:#f4f2ea; --card:#fffefa; --ink:#2c2c2a; --line:#3a3a37;
  --muted:#8c8a82; --sub:#b6b3a8; --accent:#2f6fb0; --accent-soft:#dbe7f3;
  --go:#3f9b57; --go-soft:#dcefe0; --warn:#d98b2b; --warn-soft:#f6e7cf;
  --stop:#cf4b3f; --stop-soft:#f6dcd8; --shadow:rgba(40,40,36,.18);
"""

TEMA_ESCURO = """
  --paper:#14181b; --card:#1d2327; --ink:#e9e7df; --line:#aeb5b8;
  --muted:#8b9398; --sub:#4a5258; --accent:#5fa3df; --accent-soft:#21333f;
  --go:#5cc079; --go-soft:#1f3326; --warn:#e0a64d; --warn-soft:#3a2f1c;
  --stop:#e8695c; --stop-soft:#3a221f; --shadow:rgba(0,0,0,.5);
"""

# Estilos invariantes (cópia fiel do wireframe, restritos à Direção C) + overrides
# para o chrome do Streamlit, de forma que o "papel" cubra a página inteira.
CSS_BASE = """
  @import url('https://fonts.googleapis.com/css2?family=Patrick+Hand&family=Caveat:wght@600;700&display=swap');

  /* ---- chrome do Streamlit: papel cobrindo tudo ---- */
  .stApp { background:var(--paper); color:var(--ink); }
  header[data-testid="stHeader"] { background:transparent; }
  [data-testid="stSidebar"] { background:var(--card); border-right:1.8px dashed var(--line); }
  .block-container { padding-top:1.4rem; max-width:1080px; }
  .stApp, .stApp p, .stApp label, .stApp div {
    font-family:'Patrick Hand', system-ui, sans-serif;
  }
  /* os ícones do Streamlit usam ligaduras da fonte Material Symbols; NÃO podem herdar
     a fonte manuscrita, senão o nome do ícone vaza como texto (keyboard_double_arrow_right) */
  [data-testid="stIconMaterial"], [class*="material-icons"], [class*="material-symbols"]{
    font-family:'Material Symbols Rounded','Material Symbols Outlined',
                'Material Icons Round','Material Icons' !important;
  }

  /* contraste dos widgets nos dois temas (Streamlit não sabe do nosso toggle) */
  [data-testid="stSidebar"] *,
  [data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] *,
  .stRadio label, .stRadio div, .stMarkdown, .stMarkdown p,
  .stCaption, [data-testid="stCaptionContainer"] { color:var(--ink) !important; }
  /* campos de texto / número / select */
  .stTextInput input, .stNumberInput input, [data-baseweb="select"] > div {
    background:var(--card) !important; color:var(--ink) !important;
    border:1.6px solid var(--line) !important; border-radius:9px !important;
  }
  /* botão primário "Buscar previsão" */
  .stButton button[kind="primary"]{
    background:var(--accent) !important; color:#fff !important;
    border:none !important; border-radius:10px !important;
    font-family:'Patrick Hand',sans-serif !important; font-weight:700 !important;
  }
  /* expander dos gráficos */
  [data-testid="stExpander"] summary { color:var(--ink) !important; }

  .sk{
    background:var(--card);
    border:1.8px solid var(--line);
    border-radius:16px 11px 18px 9px / 9px 17px 10px 16px;
    box-shadow:2.5px 3px 0 var(--shadow);
  }
  .emoji{font-family:'Segoe UI Emoji','Noto Color Emoji',sans-serif;}
  .lbl{font-size:14px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;}

  /* status colors */
  .s-go{--c:var(--go);--cs:var(--go-soft);}
  .s-warn{--c:var(--warn);--cs:var(--warn-soft);}
  .s-stop{--c:var(--stop);--cs:var(--stop-soft);}
  .s-info{--c:var(--accent);--cs:var(--accent-soft);}

  /* título */
  .app-title{display:flex;align-items:center;gap:12px;margin:2px 4px 4px;}
  .app-title .logo{
    width:46px;height:46px;display:grid;place-items:center;font-size:26px;flex:0 0 auto;
    border:1.8px solid var(--line);border-radius:14px 9px 15px 10px;background:var(--accent-soft);
  }
  .app-title h1{font-family:'Patrick Hand',sans-serif;font-size:36px;margin:0;line-height:1.15;font-weight:700;}
  .app-sub{margin:0 4px 2px;color:var(--muted);font-size:16px;}
  .loc{margin:0 4px 18px;font-size:15px;color:var(--muted);}
  .loc b{color:var(--ink);font-weight:400;}

  h3.sec{
    font-family:'Patrick Hand',sans-serif;font-size:24px;line-height:1.3;
    margin:26px 4px 14px;font-weight:700;display:flex;align-items:center;gap:8px;color:var(--ink);
  }
  h3.sec::before{content:"";width:9px;height:9px;border-radius:50%;background:var(--accent);}

  /* herói */
  .hero{
    padding:26px 24px;display:grid;grid-template-columns:1.2fr 1fr;gap:18px;align-items:center;
    background:linear-gradient(135deg,var(--accent-soft),var(--card));
  }
  .hero .big{font-family:'Patrick Hand',sans-serif;font-size:78px;font-weight:700;line-height:1;color:var(--ink);}
  .hero .big small{font-size:30px;}
  .hero .cond{font-size:20px;margin-top:4px;color:var(--ink);}
  .hero .right{display:flex;flex-direction:column;gap:9px;}
  .hero .r-row{display:flex;justify-content:space-between;font-size:16px;border-bottom:1.4px dashed var(--line);padding-bottom:6px;color:var(--ink);}
  .hero .scene{font-size:64px;text-align:center;}

  /* chips */
  .chips{display:flex;flex-wrap:wrap;gap:10px;margin:0 4px;}
  .pill{
    display:inline-flex;align-items:center;gap:6px;font-size:16px;padding:6px 14px;
    border:1.6px solid var(--c);border-radius:999px;background:var(--card);color:var(--c);
  }
  .pill b{color:var(--ink);}

  /* cards de veredito */
  .verdicts{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:14px;}
  .vcard{padding:16px;display:flex;flex-direction:column;gap:8px;border-top:6px solid var(--c);}
  .vcard .top{display:flex;align-items:center;justify-content:space-between;gap:8px;}
  .vcard .name{font-size:18px;color:var(--ink);}
  .vcard .badge{
    font-family:'Patrick Hand',sans-serif;font-size:20px;line-height:1.3;font-weight:700;
    color:#fff;background:var(--c);padding:2px 12px;border-radius:999px;white-space:nowrap;
  }
  .vcard .why{font-size:15px;color:var(--muted);line-height:1.4;}
  .vcard .ico{
    width:38px;height:38px;border-radius:50%;display:grid;place-items:center;font-size:20px;
    background:var(--cs);border:1.6px solid var(--c);
  }

  /* resumo da IA — parágrafo longo: fonte legível (não a manuscrita) */
  .ai{padding:16px 18px;display:flex;gap:14px;align-items:flex-start;border-left:6px solid var(--accent);}
  .ai .face{font-size:26px;}
  .ai p{
    margin:0;color:var(--ink);
    font-family:'Segoe UI', system-ui, -apple-system, 'Helvetica Neue', Arial, sans-serif !important;
    font-size:16px;line-height:1.6;letter-spacing:.1px;
  }
  .ai.s-warn{border-left-color:var(--warn);}

  /* previsão em cartões */
  .fc-cards{display:flex;gap:12px;overflow-x:auto;padding-bottom:6px;}
  .fc-card{min-width:104px;flex:0 0 auto;padding:14px 12px;text-align:center;display:flex;flex-direction:column;gap:6px;align-items:center;}
  .fc-card .d{font-size:15px;color:var(--muted);}
  .fc-card .e{font-size:30px;}
  .fc-card .t{font-family:'Patrick Hand',sans-serif;font-size:20px;color:var(--ink);}
  .fc-card .mm{font-size:13px;color:var(--accent);}

  @media(max-width:760px){
    .hero{grid-template-columns:1fr;text-align:center;}
    .hero .scene{font-size:48px;}
    .verdicts{grid-template-columns:1fr 1fr;}
    .app-title h1{font-size:32px;}
  }
"""

# --------------------------------------------------------------------------- #
# Mapas de status → semáforo e emoji por tema (vereditos)
# --------------------------------------------------------------------------- #

# status (rules_service) → (classe de cor, badge curto)
STATUS_INFO: dict[str, tuple[str, str]] = {
    "recomendado": ("s-go", "Pode pulverizar"),
    "nao_recomendado": ("s-stop", "Evite hoje"),
    "sugerida": ("s-warn", "Irrigar"),
    "nao_necessaria": ("s-go", "Não precisa"),
    "risco": ("s-stop", "Risco de geada"),
    "sem_risco": ("s-go", "Sem risco"),
    "alerta": ("s-warn", "Chuva forte"),
    "normal": ("s-go", "Tranquilo"),
}

# tema (chave do dict de vereditos) → (emoji, nome amigável)
TEMA_INFO: dict[str, tuple[str, str]] = {
    "pulverizacao": ("🌫️", "Pulverização"),
    "irrigacao": ("💧", "Irrigação"),
    "geada": ("❄️", "Geada"),
    "chuva_forte": ("⛈️", "Chuva forte"),
}

DIAS_SEMANA = [
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
]


# --------------------------------------------------------------------------- #
# CSS / tema
# --------------------------------------------------------------------------- #


def injetar_css(tema: str) -> None:
    """Injeta o tema escolhido ('claro'/'escuro') + o CSS base no Streamlit."""
    variaveis = TEMA_ESCURO if tema == "escuro" else TEMA_CLARO
    st.markdown(
        f"<style>:root{{{variaveis}}}\n{CSS_BASE}</style>",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# Helpers de formatação (linguagem do produtor leigo)
# --------------------------------------------------------------------------- #


def nome_do_dia(iso: str) -> str:
    """Transforma '2026-06-06' em 'Hoje', 'Amanhã' ou o dia da semana."""
    d = datetime.strptime(iso, "%Y-%m-%d").date()
    delta = (d - date.today()).days
    if delta == 0:
        return "Hoje"
    if delta == 1:
        return "Amanhã"
    return DIAS_SEMANA[d.weekday()].capitalize()


def resumo_chuva(mm: float | None, prob: float | None) -> tuple[str, str]:
    """Traduz a chuva do dia em (emoji, frase simples) para leigos."""
    mm = mm or 0.0
    prob = prob or 0.0
    if mm >= 20:
        return "⛈️", f"Chuva forte — cerca de {mm:.0f} mm"
    if mm >= 5:
        return "🌧️", f"Vai chover — cerca de {mm:.0f} mm"
    if mm >= 1:
        return "🌦️", f"Chuva fraca — cerca de {mm:.0f} mm"
    if prob >= 50:
        return "🌥️", "Pode cair uma pancada"
    return "☀️", "Sem chuva"


# --------------------------------------------------------------------------- #
# Blocos de HTML (Direção C)
# --------------------------------------------------------------------------- #


def _clean(html: str) -> str:
    """Colapsa o HTML em uma única linha sem indentação.

    Indispensável: o renderizador de markdown do Streamlit trata linhas indentadas
    (4+ espaços) como bloco de código e mostraria o HTML cru em vez de renderizá-lo.
    """
    return "".join(linha.strip() for linha in html.splitlines())


def bloco_titulo(cidade: str, fuso: str) -> str:
    """Logo + título + subtítulo + local."""
    return _clean(f"""
    <div class="app-title">
      <div class="logo emoji">🌾</div>
      <h1>Clima Agro</h1>
    </div>
    <p class="app-sub">Recomendações agrícolas a partir da previsão do tempo.</p>
    <p class="loc">📍 <b>{cidade}</b> · fuso {fuso}</p>""")


def bloco_heroi(previsao: Previsao) -> str:
    """Herói: temperatura gigante + condição + umidade/vento/chuva."""
    a = previsao.current
    d = previsao.daily
    chuva_hoje = d.precipitation_sum[0] if d.precipitation_sum else 0.0
    prob_hoje = (
        d.precipitation_probability_max[0]
        if d.precipitation_probability_max
        else 0.0
    )
    emoji, frase = resumo_chuva(chuva_hoje, prob_hoje)
    chance = f" · chance {prob_hoje:.0f}%" if (prob_hoje or 0) >= 50 else ""
    return _clean(f"""
    <div class="hero sk">
      <div>
        <div class="lbl">agora</div>
        <div class="big">{a.temperature_2m:.0f}<small>°C</small></div>
        <div class="cond"><span class="emoji">{emoji}</span> {frase}{chance}</div>
      </div>
      <div class="right">
        <div class="scene emoji">{emoji}</div>
        <div class="r-row"><span>💧 Umidade</span><b>{a.relative_humidity_2m:.0f}%</b></div>
        <div class="r-row"><span>🌬️ Vento</span><b>{a.wind_speed_10m:.0f} km/h</b></div>
        <div class="r-row"><span>🌧️ Chuva hoje</span><b>{chuva_hoje:.0f} mm</b></div>
      </div>
    </div>""")


def _meta_veredito(tema: str, v: Veredito) -> tuple[str, str, str, str]:
    """Devolve (emoji, nome, classe_cor, badge) para um veredito."""
    emoji, nome = TEMA_INFO.get(tema, ("•", tema))
    classe, badge = STATUS_INFO.get(v.status, ("s-info", v.status))
    return emoji, nome, classe, badge


def bloco_chips(vereditos: dict[str, Veredito]) -> str:
    """Recomendações como chips coloridos (resumo rápido)."""
    chips = "".join(
        f'<span class="pill {classe}"><span class="emoji">{emoji}</span> '
        f"{nome}: <b>{badge}</b></span>"
        for tema, v in vereditos.items()
        for emoji, nome, classe, badge in [_meta_veredito(tema, v)]
    )
    return _clean(f'<div class="chips">{chips}</div>')


def bloco_cards(vereditos: dict[str, Veredito]) -> str:
    """Cards de veredito com semáforo de cor."""
    cards = "".join(
        _clean(f"""
        <div class="vcard sk {classe}">
          <div class="top">
            <span class="ico emoji">{emoji}</span>
            <span class="badge">{badge}</span>
          </div>
          <div class="name">{nome}</div>
          <div class="why">{v.motivo}</div>
        </div>""")
        for tema, v in vereditos.items()
        for emoji, nome, classe, badge in [_meta_veredito(tema, v)]
    )
    return _clean(f'<div class="verdicts">{cards}</div>')


def bloco_resumo(texto: str, usou_llm: bool) -> str:
    """Caixa com 🧑‍🌾 e o resumo da IA (âmbar quando veio do fallback)."""
    classe = "" if usou_llm else "s-warn"
    return _clean(f"""
    <div class="ai sk {classe}">
      <span class="face emoji">🧑‍🌾</span>
      <p>{texto}</p>
    </div>""")


def bloco_previsao(previsao: Previsao, n: int = 7) -> str:
    """Cartões horizontais com a previsão dos próximos dias."""
    d = previsao.daily
    cartoes = []
    for i in range(min(n, len(d.time))):
        emoji, _ = resumo_chuva(
            d.precipitation_sum[i], d.precipitation_probability_max[i]
        )
        mm = d.precipitation_sum[i] or 0.0
        mm_txt = f"{mm:.0f} mm" if mm >= 1 else "—"
        tmin = d.temperature_2m_min[i]
        tmax = d.temperature_2m_max[i]
        cartoes.append(
            _clean(f"""
            <div class="fc-card sk">
              <span class="d">{nome_do_dia(d.time[i])}</span>
              <span class="e emoji">{emoji}</span>
              <span class="t">{tmin:.0f}° a {tmax:.0f}°</span>
              <span class="mm">{mm_txt}</span>
            </div>""")
        )
    return _clean(f'<div class="fc-cards">{"".join(cartoes)}</div>')
