"""Gráficos Plotly para a interface (Fase 4).

Cada função recebe a `Previsao` validada e devolve uma figura Plotly pronta para
`st.plotly_chart`. Não há cálculo de regra aqui — apenas visualização dos dados.
"""

from __future__ import annotations

import plotly.graph_objects as go

from weather_service import Previsao


def grafico_chuva(previsao: Previsao) -> go.Figure:
    """Volume de chuva (barras, mm) e probabilidade máxima (linha, %) por dia."""
    d = previsao.daily
    fig = go.Figure()
    fig.add_bar(
        x=d.time,
        y=d.precipitation_sum,
        name="Volume (mm)",
        marker_color="#1f77b4",
        yaxis="y",
    )
    fig.add_scatter(
        x=d.time,
        y=d.precipitation_probability_max,
        name="Probabilidade (%)",
        mode="lines+markers",
        marker_color="#ff7f0e",
        yaxis="y2",
    )
    fig.update_layout(
        title="Chuva por dia",
        xaxis_title="Dia",
        yaxis=dict(title="Volume (mm)", side="left"),
        yaxis2=dict(
            title="Probabilidade (%)",
            overlaying="y",
            side="right",
            range=[0, 100],
        ),
        legend=dict(orientation="h", y=1.1),
        margin=dict(t=60, b=40),
    )
    return fig


def grafico_temperatura(previsao: Previsao) -> go.Figure:
    """Temperatura mínima e máxima por dia (faixa entre as duas)."""
    d = previsao.daily
    fig = go.Figure()
    fig.add_scatter(
        x=d.time,
        y=d.temperature_2m_max,
        name="Máxima (°C)",
        mode="lines+markers",
        line=dict(color="#d62728"),
    )
    fig.add_scatter(
        x=d.time,
        y=d.temperature_2m_min,
        name="Mínima (°C)",
        mode="lines+markers",
        line=dict(color="#1f77b4"),
        fill="tonexty",
        fillcolor="rgba(31,119,180,0.1)",
    )
    fig.update_layout(
        title="Temperatura por dia",
        xaxis_title="Dia",
        yaxis_title="Temperatura (°C)",
        legend=dict(orientation="h", y=1.1),
        margin=dict(t=60, b=40),
    )
    return fig
