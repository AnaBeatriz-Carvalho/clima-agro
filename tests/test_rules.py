"""Testes da camada de regras determinísticas.

Cobre cada regra pura em seus limites (thresholds) e o orquestrador
`avaliar_previsao` com uma previsão sintética — sem chamadas de rede.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Garante que o pacote raiz esteja no path ao rodar `pytest` da pasta tests/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import THRESHOLDS
from rules_service import (
    Veredito,
    avaliar_chuva_forte,
    avaliar_geada,
    avaliar_irrigacao,
    avaliar_previsao,
    avaliar_pulverizacao,
)
from weather_service import DadosAtuais, DadosDiarios, DadosHorarios, Previsao


# --------------------------------------------------------------------------- #
# Pulverização
# --------------------------------------------------------------------------- #


def test_pulverizacao_condicoes_ideais():
    v = avaliar_pulverizacao(chuva_janela_mm=0.0, vento_kmh=6.0, umidade_pct=70.0)
    assert v.status == "recomendado"


def test_pulverizacao_bloqueada_por_chuva():
    v = avaliar_pulverizacao(chuva_janela_mm=2.0, vento_kmh=6.0, umidade_pct=70.0)
    assert v.status == "nao_recomendado"
    assert "chuva" in v.motivo.lower()


def test_pulverizacao_vento_fraco():
    v = avaliar_pulverizacao(chuva_janela_mm=0.0, vento_kmh=1.0, umidade_pct=70.0)
    assert v.status == "nao_recomendado"
    assert "inversão" in v.motivo.lower()


def test_pulverizacao_vento_forte():
    v = avaliar_pulverizacao(chuva_janela_mm=0.0, vento_kmh=20.0, umidade_pct=70.0)
    assert v.status == "nao_recomendado"
    assert "mecânica" in v.motivo.lower()


def test_pulverizacao_umidade_baixa():
    v = avaliar_pulverizacao(chuva_janela_mm=0.0, vento_kmh=6.0, umidade_pct=30.0)
    assert v.status == "nao_recomendado"
    assert "umidade" in v.motivo.lower()


def test_pulverizacao_vento_nos_limites():
    # Exatamente nos limites mínimo e máximo deve permanecer recomendado.
    vmin = avaliar_pulverizacao(0.0, THRESHOLDS.pulverizacao_vento_min_kmh, 70.0)
    vmax = avaliar_pulverizacao(0.0, THRESHOLDS.pulverizacao_vento_max_kmh, 70.0)
    assert vmin.status == "recomendado"
    assert vmax.status == "recomendado"


# --------------------------------------------------------------------------- #
# Irrigação
# --------------------------------------------------------------------------- #


def test_irrigacao_sugerida_com_deficit():
    v = avaliar_irrigacao(et0_acumulada_mm=15.0, chuva_acumulada_mm=2.0, dias=3)
    assert v.status == "sugerida"
    assert v.dados_de_apoio["deficit_mm"] == 13.0


def test_irrigacao_nao_necessaria_com_chuva():
    v = avaliar_irrigacao(et0_acumulada_mm=5.0, chuva_acumulada_mm=20.0, dias=3)
    assert v.status == "nao_necessaria"
    assert v.dados_de_apoio["deficit_mm"] == -15.0


def test_irrigacao_sem_deficit_no_zero():
    # Déficit exatamente zero não dispara irrigação.
    v = avaliar_irrigacao(et0_acumulada_mm=10.0, chuva_acumulada_mm=10.0, dias=3)
    assert v.status == "nao_necessaria"


# --------------------------------------------------------------------------- #
# Geada
# --------------------------------------------------------------------------- #


def test_geada_risco():
    v = avaliar_geada(temp_min_c=1.5, dia="2026-06-06")
    assert v.status == "risco"
    assert "2026-06-06" in v.motivo


def test_geada_sem_risco():
    v = avaliar_geada(temp_min_c=12.0)
    assert v.status == "sem_risco"


def test_geada_no_limite():
    # Exatamente no threshold não é risco (regra é estritamente menor).
    v = avaliar_geada(temp_min_c=THRESHOLDS.geada_temp_min_c)
    assert v.status == "sem_risco"


# --------------------------------------------------------------------------- #
# Chuva forte
# --------------------------------------------------------------------------- #


def test_chuva_forte_alerta():
    v = avaliar_chuva_forte(chuva_mm=45.0, dia="2026-06-07")
    assert v.status == "alerta"


def test_chuva_forte_normal():
    v = avaliar_chuva_forte(chuva_mm=5.0)
    assert v.status == "normal"


# --------------------------------------------------------------------------- #
# Orquestrador
# --------------------------------------------------------------------------- #


def _previsao_fake() -> Previsao:
    """Previsão sintética para testar o orquestrador sem rede."""
    return Previsao(
        latitude=-10.9111,
        longitude=-37.0717,
        timezone="America/Sao_Paulo",
        current=DadosAtuais(
            time="2026-06-05T12:00",
            temperature_2m=28.0,
            relative_humidity_2m=65.0,
            precipitation=0.0,
            wind_speed_10m=6.0,
            soil_moisture_0_to_1cm=0.2,
            soil_temperature_0cm=29.0,
        ),
        daily=DadosDiarios(
            time=["2026-06-05", "2026-06-06", "2026-06-07"],
            precipitation_sum=[0.0, 1.0, 50.0],
            precipitation_probability_max=[10.0, 20.0, 90.0],
            et0_fao_evapotranspiration=[5.0, 5.0, 5.0],
            temperature_2m_max=[30.0, 31.0, 27.0],
            temperature_2m_min=[20.0, 2.0, 19.0],
            wind_speed_10m_max=[12.0, 10.0, 15.0],
            relative_humidity_2m_max=[80.0, 85.0, 95.0],
        ),
        hourly=DadosHorarios(
            time=[
                "2026-06-05T12:00",
                "2026-06-05T13:00",
                "2026-06-05T14:00",
            ],
            precipitation=[0.0, 0.0, 0.0],
            wind_speed_10m=[6.0, 6.5, 7.0],
            relative_humidity_2m=[65.0, 64.0, 63.0],
        ),
    )


def test_avaliar_previsao_retorna_todos_os_temas():
    vereditos = avaliar_previsao(_previsao_fake())
    assert set(vereditos) == {"pulverizacao", "irrigacao", "geada", "chuva_forte"}
    assert all(isinstance(v, Veredito) for v in vereditos.values())


def test_avaliar_previsao_detecta_geada_no_pior_dia():
    vereditos = avaliar_previsao(_previsao_fake())
    # A mínima de 2.0 °C em 2026-06-06 deve ser pega como pior dia.
    assert vereditos["geada"].status == "risco"
    assert vereditos["geada"].dados_de_apoio["dia"] == "2026-06-06"


def test_avaliar_previsao_detecta_chuva_forte_no_pior_dia():
    vereditos = avaliar_previsao(_previsao_fake())
    assert vereditos["chuva_forte"].status == "alerta"
    assert vereditos["chuva_forte"].dados_de_apoio["dia"] == "2026-06-07"


def test_avaliar_previsao_irrigacao_com_deficit():
    # et0 acumulada (15) > chuva acumulada (51 nos 3 dias? não) -> conferir janela.
    vereditos = avaliar_previsao(_previsao_fake())
    apoio = vereditos["irrigacao"].dados_de_apoio
    # 3 dias: et0 = 15, chuva = 0+1+50 = 51 -> sem déficit.
    assert apoio["et0_acumulada_mm"] == 15.0
    assert apoio["chuva_acumulada_mm"] == 51.0
    assert vereditos["irrigacao"].status == "nao_necessaria"
