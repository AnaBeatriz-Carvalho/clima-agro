"""Camada de regras determinísticas.

Aqui acontecem TODOS os cálculos e decisões numéricas — de forma testável, sem
LLM. Cada regra recebe valores já extraídos e devolve um `Veredito` estruturado
(status + motivo + dados de apoio). Esses vereditos são o input da LLM, que apenas
os traduz para linguagem do produtor — nunca recalcula.

As regras puras (`avaliar_*`) operam sobre números simples, o que as torna
trivialmente testáveis. O orquestrador `avaliar_previsao` extrai esses números do
objeto `Previsao` e chama cada regra.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from config import THRESHOLDS, Thresholds
from weather_service import Previsao


@dataclass
class Veredito:
    """Resultado estruturado de uma regra.

    Attributes:
        status: rótulo curto e estável da decisão (ex.: "recomendado").
        motivo: explicação determinística do porquê (em PT-BR).
        dados_de_apoio: números que sustentam a decisão, para a LLM citar.
    """

    status: str
    motivo: str
    dados_de_apoio: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Converte para dict — formato consumido pela camada LLM."""
        return asdict(self)


# --------------------------------------------------------------------------- #
# Regras puras
# --------------------------------------------------------------------------- #


def avaliar_pulverizacao(
    chuva_janela_mm: float,
    vento_kmh: float,
    umidade_pct: float,
    th: Thresholds = THRESHOLDS,
) -> Veredito:
    """Decide se é bom momento para pulverizar.

    Condições ideais: chuva ~0 na janela, vento entre o mínimo e o máximo
    (nem inversão térmica, nem deriva mecânica) e umidade acima do mínimo.
    """
    apoio = {
        "chuva_janela_mm": chuva_janela_mm,
        "vento_kmh": vento_kmh,
        "umidade_pct": umidade_pct,
    }

    if chuva_janela_mm > th.pulverizacao_chuva_max_mm:
        return Veredito(
            "nao_recomendado",
            f"Há chuva prevista na janela ({chuva_janela_mm} mm); o produto pode "
            "ser lavado.",
            apoio,
        )
    if vento_kmh < th.pulverizacao_vento_min_kmh:
        return Veredito(
            "nao_recomendado",
            f"Vento muito fraco ({vento_kmh} km/h); risco de deriva por inversão "
            "térmica.",
            apoio,
        )
    if vento_kmh > th.pulverizacao_vento_max_kmh:
        return Veredito(
            "nao_recomendado",
            f"Vento forte ({vento_kmh} km/h); risco de deriva mecânica.",
            apoio,
        )
    if umidade_pct < th.pulverizacao_umidade_min:
        return Veredito(
            "nao_recomendado",
            f"Umidade relativa baixa ({umidade_pct}%); maior evaporação e deriva.",
            apoio,
        )
    return Veredito(
        "recomendado",
        f"Sem chuva na janela, vento de {vento_kmh} km/h e umidade de "
        f"{umidade_pct}% — condições favoráveis.",
        apoio,
    )


def avaliar_irrigacao(
    et0_acumulada_mm: float,
    chuva_acumulada_mm: float,
    dias: int,
    th: Thresholds = THRESHOLDS,
) -> Veredito:
    """Balanço hídrico simples: déficit = evapotranspiração - chuva no período."""
    deficit = round(et0_acumulada_mm - chuva_acumulada_mm, 2)
    apoio = {
        "et0_acumulada_mm": round(et0_acumulada_mm, 2),
        "chuva_acumulada_mm": round(chuva_acumulada_mm, 2),
        "deficit_mm": deficit,
        "dias": dias,
    }

    if deficit > th.irrigacao_deficit_min_mm:
        return Veredito(
            "sugerida",
            f"Em {dias} dias a evapotranspiração ({et0_acumulada_mm:.1f} mm) supera "
            f"a chuva ({chuva_acumulada_mm:.1f} mm); déficit de {deficit:.1f} mm.",
            apoio,
        )
    return Veredito(
        "nao_necessaria",
        f"A chuva prevista ({chuva_acumulada_mm:.1f} mm) cobre a "
        f"evapotranspiração ({et0_acumulada_mm:.1f} mm) em {dias} dias.",
        apoio,
    )


def avaliar_geada(
    temp_min_c: float,
    dia: str | None = None,
    th: Thresholds = THRESHOLDS,
) -> Veredito:
    """Alerta de geada quando a temperatura mínima fica abaixo do limite."""
    apoio = {"temperatura_min_c": temp_min_c, "dia": dia}
    if temp_min_c < th.geada_temp_min_c:
        return Veredito(
            "risco",
            f"Temperatura mínima de {temp_min_c} °C"
            + (f" em {dia}" if dia else "")
            + " — risco de geada.",
            apoio,
        )
    return Veredito(
        "sem_risco",
        f"Temperatura mínima de {temp_min_c} °C — sem risco de geada.",
        apoio,
    )


def avaliar_chuva_forte(
    chuva_mm: float,
    dia: str | None = None,
    th: Thresholds = THRESHOLDS,
) -> Veredito:
    """Alerta de chuva forte quando o acumulado diário excede o limite."""
    apoio = {"chuva_mm": chuva_mm, "dia": dia}
    if chuva_mm > th.chuva_forte_mm:
        return Veredito(
            "alerta",
            f"Previsão de {chuva_mm} mm"
            + (f" em {dia}" if dia else "")
            + " — chuva forte.",
            apoio,
        )
    return Veredito(
        "normal",
        f"Acumulado de {chuva_mm} mm"
        + (f" em {dia}" if dia else "")
        + " — sem alerta de chuva forte.",
        apoio,
    )


# --------------------------------------------------------------------------- #
# Helpers de extração
# --------------------------------------------------------------------------- #


def _soma(valores: list[float | None]) -> float:
    """Soma uma série ignorando valores ausentes (None)."""
    return sum(v for v in valores if v is not None)


def _soma_chuva_proximas_horas(previsao: Previsao, horas: int) -> float:
    """Soma a precipitação horária a partir do horário atual.

    Procura na série horária o primeiro instante >= ao `current.time` e soma
    as próximas `horas` posições. Se não encontrar, soma as primeiras `horas`.
    """
    hourly = previsao.hourly
    agora = previsao.current.time
    inicio = next(
        (i for i, t in enumerate(hourly.time) if t >= agora),
        0,
    )
    janela = hourly.precipitation[inicio : inicio + horas]
    return _soma(janela)


# --------------------------------------------------------------------------- #
# Orquestrador
# --------------------------------------------------------------------------- #


def avaliar_previsao(
    previsao: Previsao,
    th: Thresholds = THRESHOLDS,
) -> dict[str, Veredito]:
    """Extrai os números do objeto `Previsao` e aplica todas as regras.

    Returns:
        Dicionário com um veredito por tema: "pulverizacao", "irrigacao",
        "geada" e "chuva_forte".
    """
    atual = previsao.current
    diario = previsao.daily
    n = th.irrigacao_dias_analise

    # Pulverização: janela de chuva das próximas horas + vento/umidade atuais.
    chuva_janela = _soma_chuva_proximas_horas(previsao, horas=6)
    vento = atual.wind_speed_10m if atual.wind_speed_10m is not None else 0.0
    umidade = (
        atual.relative_humidity_2m
        if atual.relative_humidity_2m is not None
        else 0.0
    )

    # Irrigação: balanço hídrico dos próximos `n` dias.
    et0_acum = _soma(diario.et0_fao_evapotranspiration[:n])
    chuva_acum = _soma(diario.precipitation_sum[:n])

    # Geada: dia de menor temperatura mínima na janela de previsão.
    minimas = [
        (t, v)
        for t, v in zip(diario.time, diario.temperature_2m_min)
        if v is not None
    ]
    dia_geada, temp_geada = (
        min(minimas, key=lambda par: par[1]) if minimas else (None, 0.0)
    )

    # Chuva forte: dia de maior acumulado na janela de previsão.
    chuvas = [
        (t, v)
        for t, v in zip(diario.time, diario.precipitation_sum)
        if v is not None
    ]
    dia_chuva, chuva_max = (
        max(chuvas, key=lambda par: par[1]) if chuvas else (None, 0.0)
    )

    return {
        "pulverizacao": avaliar_pulverizacao(chuva_janela, vento, umidade, th),
        "irrigacao": avaliar_irrigacao(et0_acum, chuva_acum, n, th),
        "geada": avaliar_geada(temp_geada, dia_geada, th),
        "chuva_forte": avaliar_chuva_forte(chuva_max, dia_chuva, th),
    }


if __name__ == "__main__":
    # Teste manual: busca a previsão real e imprime os vereditos.
    from weather_service import buscar_previsao

    vereditos = avaliar_previsao(buscar_previsao())
    for tema, v in vereditos.items():
        print(f"[{tema}] {v.status}\n  {v.motivo}\n  apoio: {v.dados_de_apoio}\n")
