"""Consumo da API Open-Meteo e validação dos dados climáticos.

Responsável por montar a requisição com todas as variáveis de interesse agrícola,
buscar o JSON e validá-lo com pydantic. Não toma decisões — apenas devolve uma
estrutura limpa e confiável para a camada de regras (`rules_service.py`).
"""

from __future__ import annotations

import requests
from pydantic import BaseModel, Field

import config


# --------------------------------------------------------------------------- #
# Modelos pydantic — espelham a resposta da Open-Meteo
# --------------------------------------------------------------------------- #


class DadosAtuais(BaseModel):
    """Condições do momento (`current=`)."""

    time: str
    temperature_2m: float | None = None
    relative_humidity_2m: float | None = None
    precipitation: float | None = None
    wind_speed_10m: float | None = None
    soil_moisture_0_to_1cm: float | None = None
    soil_temperature_0cm: float | None = None


class DadosDiarios(BaseModel):
    """Séries diárias (`daily=`). Cada lista é alinhada por índice com `time`."""

    time: list[str]
    precipitation_sum: list[float | None] = Field(default_factory=list)
    precipitation_probability_max: list[float | None] = Field(default_factory=list)
    et0_fao_evapotranspiration: list[float | None] = Field(default_factory=list)
    temperature_2m_max: list[float | None] = Field(default_factory=list)
    temperature_2m_min: list[float | None] = Field(default_factory=list)
    wind_speed_10m_max: list[float | None] = Field(default_factory=list)
    relative_humidity_2m_max: list[float | None] = Field(default_factory=list)


class DadosHorarios(BaseModel):
    """Séries horárias (`hourly=`) — base da janela de pulverização."""

    time: list[str]
    precipitation: list[float | None] = Field(default_factory=list)
    wind_speed_10m: list[float | None] = Field(default_factory=list)
    relative_humidity_2m: list[float | None] = Field(default_factory=list)


class Previsao(BaseModel):
    """Resposta completa e validada da Open-Meteo."""

    latitude: float
    longitude: float
    timezone: str
    current: DadosAtuais
    daily: DadosDiarios
    hourly: DadosHorarios


class Cidade(BaseModel):
    """Resultado de geocoding (Fase 5)."""

    name: str
    latitude: float
    longitude: float
    country: str | None = None
    admin1: str | None = None  # estado/região

    @property
    def rotulo(self) -> str:
        """Rótulo amigável: 'Cidade, Estado, País'."""
        partes = [p for p in (self.name, self.admin1, self.country) if p]
        return ", ".join(partes)


# --------------------------------------------------------------------------- #
# Função principal
# --------------------------------------------------------------------------- #


def _montar_parametros(lat: float, lon: float) -> dict[str, object]:
    """Monta o dicionário de query params para a Open-Meteo."""
    return {
        "latitude": lat,
        "longitude": lon,
        "timezone": config.TIMEZONE,
        "forecast_days": config.PREVISAO_DIAS,
        "daily": ",".join(config.VARIAVEIS_DIARIAS),
        "hourly": ",".join(config.VARIAVEIS_HORARIAS),
        "current": ",".join(config.VARIAVEIS_ATUAIS),
    }


def buscar_previsao(
    lat: float = config.LATITUDE_PADRAO,
    lon: float = config.LONGITUDE_PADRAO,
) -> Previsao:
    """Busca e valida a previsão da Open-Meteo para a coordenada informada.

    Args:
        lat: latitude em graus decimais.
        lon: longitude em graus decimais.

    Returns:
        Objeto `Previsao` validado.

    Raises:
        requests.HTTPError: se a API retornar status de erro.
        pydantic.ValidationError: se o JSON não tiver o formato esperado.
    """
    resposta = requests.get(
        config.OPEN_METEO_URL,
        params=_montar_parametros(lat, lon),
        timeout=config.TIMEOUT_HTTP,
    )
    resposta.raise_for_status()
    return Previsao.model_validate(resposta.json())


def buscar_cidade(nome: str, max_resultados: int = 5) -> list[Cidade]:
    """Busca coordenadas a partir do nome de uma cidade (geocoding Open-Meteo).

    Args:
        nome: nome da cidade (ex.: "Aracaju").
        max_resultados: quantos candidatos retornar.

    Returns:
        Lista de `Cidade` (vazia se nada for encontrado).
    """
    resposta = requests.get(
        config.GEOCODING_URL,
        params={
            "name": nome,
            "count": max_resultados,
            "language": "pt",
            "format": "json",
        },
        timeout=config.TIMEOUT_HTTP,
    )
    resposta.raise_for_status()
    resultados = resposta.json().get("results") or []
    return [Cidade.model_validate(r) for r in resultados]


if __name__ == "__main__":
    # Teste manual simples — imprime a previsão dos próximos dias.
    previsao = buscar_previsao()
    d = previsao.daily
    print(f"Previsão para lat={previsao.latitude}, lon={previsao.longitude} "
          f"({previsao.timezone})\n")
    print(f"{'Data':<12}{'Chuva mm':>10}{'Prob %':>8}{'Mín °C':>8}"
          f"{'Máx °C':>8}{'Vento':>8}{'ET0':>7}")
    for i, dia in enumerate(d.time):
        print(
            f"{dia:<12}"
            f"{d.precipitation_sum[i]!s:>10}"
            f"{d.precipitation_probability_max[i]!s:>8}"
            f"{d.temperature_2m_min[i]!s:>8}"
            f"{d.temperature_2m_max[i]!s:>8}"
            f"{d.wind_speed_10m_max[i]!s:>8}"
            f"{d.et0_fao_evapotranspiration[i]!s:>7}"
        )
