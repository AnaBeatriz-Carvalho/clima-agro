"""Configuração central do clima-agro.

Reúne localização padrão, parâmetros da API Open-Meteo, thresholds das regras
agronômicas e o endpoint do LM Studio. Tudo em um só lugar para facilitar ajuste.

Os thresholds agronômicos são pontos de partida — revisar com fonte técnica
(Embrapa, etc.) antes de uso real em produção.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Carrega variáveis de um arquivo .env local (se existir), sem sobrescrever as já
# definidas no ambiente. Em deploy (sem .env) isso é simplesmente ignorado.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv não instalado — segue com o ambiente do SO
    pass


# --------------------------------------------------------------------------- #
# Localização e API Open-Meteo
# --------------------------------------------------------------------------- #

# Padrão para testes: Aracaju / Sergipe.
LATITUDE_PADRAO: float = -10.9111
LONGITUDE_PADRAO: float = -37.0717
TIMEZONE: str = "America/Sao_Paulo"

OPEN_METEO_URL: str = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL: str = "https://geocoding-api.open-meteo.com/v1/search"
PREVISAO_DIAS: int = 7
TIMEOUT_HTTP: int = 20  # segundos

# Variáveis solicitadas à Open-Meteo (ver seção 4 da especificação).
VARIAVEIS_DIARIAS: list[str] = [
    "precipitation_sum",
    "precipitation_probability_max",
    "et0_fao_evapotranspiration",
    "temperature_2m_max",
    "temperature_2m_min",
    "wind_speed_10m_max",
    "relative_humidity_2m_max",
]

VARIAVEIS_HORARIAS: list[str] = [
    "precipitation",
    "wind_speed_10m",
    "relative_humidity_2m",
]

VARIAVEIS_ATUAIS: list[str] = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "wind_speed_10m",
    "soil_moisture_0_to_1cm",
    "soil_temperature_0cm",
]


# --------------------------------------------------------------------------- #
# Thresholds das regras determinísticas (seção 5)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Thresholds:
    """Limites usados pela camada de regras. Valores de partida, ajustáveis."""

    # Pulverização -----------------------------------------------------------
    pulverizacao_chuva_max_mm: float = 0.2   # chuva ~0 na janela
    pulverizacao_vento_min_kmh: float = 3.0  # abaixo: risco de inversão térmica
    pulverizacao_vento_max_kmh: float = 10.0  # acima: deriva mecânica
    pulverizacao_umidade_min: float = 50.0   # umidade relativa mínima (%)

    # Irrigação --------------------------------------------------------------
    irrigacao_dias_analise: int = 3          # janela de balanço hídrico
    irrigacao_deficit_min_mm: float = 0.0    # déficit (et0 - chuva) acima disso sugere irrigar

    # Geada ------------------------------------------------------------------
    geada_temp_min_c: float = 3.0            # temperatura mínima de alerta

    # Chuva forte ------------------------------------------------------------
    chuva_forte_mm: float = 30.0             # acumulado diário de alerta


THRESHOLDS = Thresholds()


# --------------------------------------------------------------------------- #
# Camada LLM (Fase 3) — escolha de provedor
# --------------------------------------------------------------------------- #
#
# Nenhum segredo fica no código: a chave da Gemini vem de variável de ambiente
# (GEMINI_API_KEY). Em deploy no Streamlit Cloud, defina-a em "Secrets" — o app
# faz a ponte para a variável de ambiente.
#
# Provedor: "auto"   -> usa Gemini se houver chave, senão LM Studio local.
#           "gemini" -> força Gemini (nuvem, para publicação).
#           "lmstudio" -> força LM Studio (local, sem custo, sem internet).

LLM_TEMPERATURA: float = 0.3

# Gemini (Google Generative Language API) ------------------------------------
GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/models"

# LM Studio (servidor OpenAI-compatible local, para desenvolvimento) ----------
LM_STUDIO_URL: str = "http://localhost:1234/v1/chat/completions"
LM_STUDIO_MODELO: str = "llama-3.1-8b-instruct"


# As funções abaixo leem o ambiente em tempo de chamada (não no import), para que
# o app possa injetar a chave a partir de st.secrets antes do primeiro uso.

def gemini_api_key() -> str:
    """Chave da Gemini, vinda da variável de ambiente GEMINI_API_KEY."""
    return os.environ.get("GEMINI_API_KEY", "")


def gemini_modelo() -> str:
    """Modelo Gemini (configurável por env). Padrão: gemini-flash-latest.

    Aponta para o flash mais recente — funciona no free-tier (os modelos Pro,
    como gemini-3-pro-preview, exigem billing e retornam 429 sem ele). Ajuste
    com a env GEMINI_MODELO se ativar billing e quiser um modelo Pro.
    """
    return os.environ.get("GEMINI_MODELO", "gemini-flash-latest")


def provedor_llm() -> str:
    """Provedor efetivo: "gemini", "lmstudio" ou resolução do modo "auto"."""
    provider = os.environ.get("LLM_PROVIDER", "auto").lower()
    if provider == "auto":
        return "gemini" if gemini_api_key() else "lmstudio"
    return provider
