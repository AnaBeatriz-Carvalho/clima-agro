"""Interface Streamlit do clima-agro (Fase 4).

Reúne as camadas: busca a previsão (Open-Meteo), aplica as regras determinísticas,
pede a tradução à LLM (com fallback) e mostra tudo com gráficos Plotly.

Rodar:  streamlit run app.py
"""

from __future__ import annotations

from datetime import date, datetime

import streamlit as st

import config
from ai_service import gerar_recomendacao_segura
from charts import grafico_chuva, grafico_temperatura
from rules_service import Veredito, avaliar_previsao
from weather_service import Cidade, Previsao, buscar_cidade, buscar_previsao

# Ícone por status de veredito (chave estável vinda das regras).
ICONES_STATUS: dict[str, str] = {
    "recomendado": "✅",
    "nao_recomendado": "🚫",
    "sugerida": "💧",
    "nao_necessaria": "✅",
    "risco": "⚠️",
    "sem_risco": "✅",
    "alerta": "🌧️",
    "normal": "✅",
}

TITULOS_TEMA: dict[str, str] = {
    "pulverizacao": "Pulverização",
    "irrigacao": "Irrigação",
    "geada": "Geada",
    "chuva_forte": "Chuva forte",
}

DIAS_SEMANA = [
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
]


def _nome_do_dia(iso: str) -> str:
    """Transforma '2026-06-06' em 'Hoje', 'Amanhã' ou o dia da semana."""
    d = datetime.strptime(iso, "%Y-%m-%d").date()
    delta = (d - date.today()).days
    if delta == 0:
        return "Hoje"
    if delta == 1:
        return "Amanhã"
    return DIAS_SEMANA[d.weekday()].capitalize()


def _resumo_chuva(mm: float | None, prob: float | None) -> tuple[str, str]:
    """Traduz chuva do dia em (emoji, frase simples) para leigos."""
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
# Acesso a dados (com cache para respeitar limites da Open-Meteo)
# --------------------------------------------------------------------------- #


@st.cache_data(ttl=1800, show_spinner=False)
def _buscar_cidade(nome: str) -> list[Cidade]:
    return buscar_cidade(nome)


@st.cache_data(ttl=1800, show_spinner=False)
def _buscar_previsao(lat: float, lon: float) -> Previsao:
    return buscar_previsao(lat, lon)


# --------------------------------------------------------------------------- #
# Componentes de UI
# --------------------------------------------------------------------------- #


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


def _condicoes_atuais(previsao: Previsao) -> None:
    st.subheader("Tempo agora")
    a = previsao.current
    d = previsao.daily
    # Chuva do DIA (acumulado), não a do instante — o valor instantâneo costuma
    # ser ~0 mesmo num dia chuvoso e confunde o usuário.
    chuva_hoje = d.precipitation_sum[0] if d.precipitation_sum else 0.0
    prob_hoje = d.precipitation_probability_max[0] if d.precipitation_probability_max else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Temperatura", f"{a.temperature_2m:.0f} °C")
    c2.metric("Umidade", f"{a.relative_humidity_2m:.0f} %")
    c3.metric("Vento", f"{a.wind_speed_10m:.0f} km/h")
    c4.metric("Chuva hoje", f"{chuva_hoje:.0f} mm", help="Total previsto para o dia inteiro")

    if (a.precipitation or 0) > 0:
        st.caption("🌧️ Está chovendo agora.")
    elif (prob_hoje or 0) >= 50:
        st.caption(f"☔ Chance de chuva hoje: {prob_hoje:.0f}%.")


def _previsao_amigavel(previsao: Previsao) -> None:
    """Previsão dos próximos dias em linguagem simples (emoji + frase)."""
    st.subheader("Próximos dias")
    d = previsao.daily
    for i in range(len(d.time)):
        emoji, frase = _resumo_chuva(
            d.precipitation_sum[i], d.precipitation_probability_max[i]
        )
        tmin = d.temperature_2m_min[i]
        tmax = d.temperature_2m_max[i]
        col_dia, col_tempo, col_temp = st.columns([2, 3, 2])
        col_dia.markdown(f"**{_nome_do_dia(d.time[i])}**")
        col_tempo.markdown(f"{emoji} {frase}")
        col_temp.markdown(f"🌡️ {tmin:.0f}° a {tmax:.0f}°")


def _cards_vereditos(vereditos: dict[str, Veredito]) -> None:
    st.subheader("Recomendações")
    colunas = st.columns(len(vereditos))
    for coluna, (tema, v) in zip(colunas, vereditos.items()):
        icone = ICONES_STATUS.get(v.status, "•")
        with coluna:
            st.markdown(f"**{icone} {TITULOS_TEMA.get(tema, tema)}**")
            st.caption(v.motivo)


def _texto_llm(vereditos: dict[str, Veredito], previsao: Previsao) -> None:
    st.subheader("Resumo para o produtor")
    with st.spinner("Gerando recomendação..."):
        texto, usou_llm = gerar_recomendacao_segura(vereditos, previsao)
    if usou_llm:
        st.success(texto)
    else:
        st.info(texto)
        st.caption(
            "⚠️ LM Studio offline — texto gerado pelas regras. "
            "Inicie o servidor local para o resumo em linguagem natural."
        )


# --------------------------------------------------------------------------- #
# Página
# --------------------------------------------------------------------------- #


def main() -> None:
    st.set_page_config(page_title="clima-agro", page_icon="🌾", layout="wide")
    st.title("🌾 Clima Agro")
    st.write("Recomendações agrícolas a partir da previsão do tempo.")

    lat, lon, rotulo = _seletor_local()

    if not st.sidebar.button("Buscar previsão", type="primary"):
        st.info("Defina o local na barra lateral e clique em **Buscar previsão**.")
        return

    try:
        previsao = _buscar_previsao(lat, lon)
    except Exception as exc:  # rede/validação
        st.error(f"Não foi possível buscar a previsão: {exc}")
        return

    st.caption(f"Local: {rotulo}  ·  fuso: {previsao.timezone}")
    vereditos = avaliar_previsao(previsao)

    _condicoes_atuais(previsao)
    _texto_llm(vereditos, previsao)
    _cards_vereditos(vereditos)

    st.divider()
    _previsao_amigavel(previsao)

    # Gráficos ficam recolhidos: úteis para quem quer detalhe, sem atrapalhar leigos.
    with st.expander("📊 Ver gráficos detalhados"):
        g1, g2 = st.columns(2)
        g1.plotly_chart(grafico_chuva(previsao), use_container_width=True)
        g2.plotly_chart(grafico_temperatura(previsao), use_container_width=True)


if __name__ == "__main__":
    main()
