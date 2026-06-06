"""Interface Streamlit do clima-agro (Fase 4 · redesign "Clima do dia").

Reúne as camadas: busca a previsão (Open-Meteo), aplica as regras determinísticas,
pede a tradução à LLM (com fallback) e mostra tudo no visual desenhado no Claude
Design (Direção C): herói grande, recomendações com semáforo de cor, resumo da IA e
previsão de 7 dias em cartões — com tema claro/escuro.

A camada visual (CSS + blocos HTML) vive em `ui.py`; aqui ficam só a orquestração
e o acesso a dados.

Rodar:  streamlit run app.py
"""

from __future__ import annotations

import os

import streamlit as st

# Ponte para deploy: no Streamlit Cloud, segredos definidos em "Secrets" ficam em
# st.secrets. Copiamos para variáveis de ambiente (sem sobrescrever as já
# existentes) para que config.* enxergue a chave. Roda antes de qualquer uso da LLM.
for _chave in ("GEMINI_API_KEY", "GEMINI_MODELO", "LLM_PROVIDER"):
    try:
        if _chave in st.secrets:
            os.environ.setdefault(_chave, str(st.secrets[_chave]))
    except Exception:
        pass  # sem arquivo de secrets em ambiente local — tudo bem

import config
import ui
from ai_service import gerar_recomendacao_segura
from charts import grafico_chuva, grafico_temperatura
from rules_service import avaliar_previsao
from weather_service import Cidade, Previsao, buscar_cidade, buscar_previsao


# --------------------------------------------------------------------------- #
# Acesso a dados (com cache para respeitar limites da Open-Meteo)
# --------------------------------------------------------------------------- #


@st.cache_data(ttl=1800, show_spinner=False)
def _buscar_cidade(nome: str) -> list[Cidade]:
    return buscar_cidade(nome)


@st.cache_data(ttl=1800, show_spinner=False)
def _buscar_previsao(lat: float, lon: float) -> Previsao:
    return buscar_previsao(lat, lon)


# --------------------------------------------------------------------------- #
# Controles da sidebar
# --------------------------------------------------------------------------- #


def _seletor_tema() -> str:
    """Toggle de tema claro/escuro no topo da sidebar. Retorna 'claro'/'escuro'."""
    rotulo = st.sidebar.radio(
        "Tema",
        ["☀︎ Claro", "☾ Escuro"],
        horizontal=True,
        key="tema_rotulo",
    )
    return "escuro" if "Escuro" in rotulo else "claro"


def _seletor_local() -> tuple[float, float, str]:
    """Sidebar: escolha por nome de cidade ou coordenadas. Retorna (lat, lon, rótulo)."""
    st.sidebar.header("📍 Local")
    modo = st.sidebar.radio("Como definir o local?", ["Buscar cidade", "Coordenadas"])

    if modo == "Buscar cidade":
        nome = st.sidebar.text_input("Cidade", value="Aracaju")
        if nome.strip():
            try:
                cidades = _buscar_cidade(nome.strip())
            except Exception as exc:  # rede/HTTP
                st.sidebar.error(f"Erro na busca: {exc}")
                cidades = []
            if cidades:
                escolha = st.sidebar.selectbox(
                    "Resultado", cidades, format_func=lambda c: c.rotulo
                )
                return escolha.latitude, escolha.longitude, escolha.rotulo
            st.sidebar.warning("Nenhuma cidade encontrada.")

    # Modo coordenadas (ou fallback se a busca não retornou nada).
    lat = st.sidebar.number_input("Latitude", value=config.LATITUDE_PADRAO, format="%.4f")
    lon = st.sidebar.number_input("Longitude", value=config.LONGITUDE_PADRAO, format="%.4f")
    return lat, lon, f"{lat:.4f}, {lon:.4f}"


# --------------------------------------------------------------------------- #
# Página
# --------------------------------------------------------------------------- #


def main() -> None:
    st.set_page_config(page_title="Clima Agro", page_icon="🌾", layout="wide")

    tema = _seletor_tema()
    ui.injetar_css(tema)
    st.sidebar.divider()

    lat, lon, rotulo = _seletor_local()

    if not st.sidebar.button("Buscar previsão", type="primary"):
        st.markdown(ui.bloco_titulo("—", "—"), unsafe_allow_html=True)
        st.info("Defina o local na barra lateral e clique em **Buscar previsão**.")
        return

    try:
        previsao = _buscar_previsao(lat, lon)
    except Exception as exc:  # rede/validação
        st.error(f"Não foi possível buscar a previsão: {exc}")
        return

    vereditos = avaliar_previsao(previsao)

    # Título + local
    st.markdown(ui.bloco_titulo(rotulo, previsao.timezone), unsafe_allow_html=True)

    # Herói (tempo agora)
    st.markdown(ui.bloco_heroi(previsao), unsafe_allow_html=True)

    # Recomendações de hoje: chips (resumo) + cards (semáforo)
    st.markdown('<h3 class="sec">Recomendações de hoje</h3>', unsafe_allow_html=True)
    st.markdown(ui.bloco_chips(vereditos), unsafe_allow_html=True)
    st.markdown(ui.bloco_cards(vereditos), unsafe_allow_html=True)

    # Resumo da IA
    st.markdown('<h3 class="sec">Resumo para o produtor</h3>', unsafe_allow_html=True)
    with st.spinner("Gerando recomendação..."):
        texto, usou_llm = gerar_recomendacao_segura(vereditos, previsao)
    st.markdown(ui.bloco_resumo(texto, usou_llm), unsafe_allow_html=True)
    if not usou_llm:
        st.caption(
            "⚠️ IA indisponível — texto gerado pelas regras. "
            "Configure a chave da Gemini (GEMINI_API_KEY) ou rode o LM Studio local "
            "para o resumo em linguagem natural."
        )

    # Previsão dos próximos 7 dias
    st.markdown('<h3 class="sec">7 dias</h3>', unsafe_allow_html=True)
    st.markdown(ui.bloco_previsao(previsao), unsafe_allow_html=True)

    # Gráficos ficam recolhidos: úteis para quem quer detalhe, sem atrapalhar leigos.
    with st.expander("📊 Ver gráficos detalhados"):
        g1, g2 = st.columns(2)
        g1.plotly_chart(grafico_chuva(previsao), width="stretch")
        g2.plotly_chart(grafico_temperatura(previsao), width="stretch")


if __name__ == "__main__":
    main()
