"""API REST do clima-agro — expõe os dados para um front-end externo.

Disponibiliza, via HTTP/JSON, as mesmas camadas que o app Streamlit já usa:

- **Dados de tempo** (Open-Meteo): busca de cidade e previsão crua.
- **Dados tratados com IA**: os vereditos determinísticos (`rules_service`) e a
  recomendação em linguagem natural (`ai_service`, com fallback offline).

O front (feito separadamente) consome estes endpoints. Por isso o CORS é liberado.
Documentação interativa automática em `/docs` (Swagger) e `/redoc`.

Rodar:  uvicorn api:app --reload
        # ou:  uvicorn api:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import time

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

import config
from ai_service import gerar_recomendacao_segura
from rules_service import Veredito, avaliar_previsao
from weather_service import Cidade, Previsao, buscar_cidade, buscar_previsao

app = FastAPI(
    title="Clima Agro API",
    version="1.0.0",
    description=(
        "Expõe os dados climáticos (Open-Meteo) e as recomendações agrícolas — "
        "vereditos determinísticos + resumo da IA (com fallback offline). "
        "Consumida por um front-end externo."
    ),
)

# Front-end roda em outra origem (porta/host diferentes), então liberamos CORS.
# Em produção, troque allow_origins por uma lista com o domínio real do front.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Modelos de resposta (documentam o JSON no /docs para o front)
# --------------------------------------------------------------------------- #


class VereditoOut(BaseModel):
    """Resultado de uma regra agronômica (espelha `rules_service.Veredito`)."""

    status: str = Field(..., description="Rótulo estável da decisão, ex.: 'recomendado'.")
    motivo: str = Field(..., description="Explicação determinística em PT-BR.")
    dados_de_apoio: dict = Field(
        default_factory=dict, description="Números que sustentam a decisão."
    )


class RecomendacaoOut(BaseModel):
    """Texto final para o produtor."""

    texto: str = Field(..., description="Resumo em linguagem natural.")
    usou_llm: bool = Field(
        ..., description="True se veio da IA; False se é o fallback determinístico."
    )


class RecomendacaoCompleta(BaseModel):
    """Camada 'tratada com IA': vereditos + recomendação."""

    vereditos: dict[str, VereditoOut]
    recomendacao: RecomendacaoOut


class ClimaCompleto(BaseModel):
    """Payload completo para o front montar a tela em uma só chamada."""

    previsao: Previsao
    vereditos: dict[str, VereditoOut]
    recomendacao: RecomendacaoOut


# --------------------------------------------------------------------------- #
# Cache simples em memória (TTL) — protege limites da Open-Meteo e a cota da IA
# --------------------------------------------------------------------------- #

_CACHE_TTL = 1800  # 30 min, igual ao cache do app Streamlit
_cache: dict[str, tuple[float, object]] = {}


def _cache_get(chave: str):
    item = _cache.get(chave)
    if item and (time.time() - item[0]) < _CACHE_TTL:
        return item[1]
    return None


def _cache_set(chave: str, valor: object) -> None:
    _cache[chave] = (time.time(), valor)


def _previsao_cacheada(lat: float, lon: float) -> Previsao:
    """Busca a previsão usando cache por coordenada (arredondada) com TTL."""
    chave = f"previsao:{lat:.4f},{lon:.4f}"
    cacheada = _cache_get(chave)
    if cacheada is not None:
        return cacheada  # type: ignore[return-value]
    try:
        previsao = buscar_previsao(lat, lon)
    except Exception as exc:  # rede/validação Open-Meteo
        raise HTTPException(
            status_code=502, detail=f"Falha ao buscar a previsão: {exc}"
        ) from exc
    _cache_set(chave, previsao)
    return previsao


def _vereditos_out(previsao: Previsao) -> dict[str, VereditoOut]:
    vereditos: dict[str, Veredito] = avaliar_previsao(previsao)
    return {tema: VereditoOut(**v.to_dict()) for tema, v in vereditos.items()}


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #


@app.get("/", include_in_schema=False)
def raiz() -> RedirectResponse:
    """Redireciona a URL base para a documentação interativa (evita 404 na raiz)."""
    return RedirectResponse(url="/docs")


@app.get("/saude", tags=["meta"], summary="Health check")
def saude() -> dict:
    """Confirma que a API está de pé e qual provedor de IA está ativo."""
    return {"status": "ok", "provedor_llm": config.provedor_llm()}


@app.get(
    "/cidades",
    response_model=list[Cidade],
    tags=["tempo"],
    summary="Busca cidades por nome (geocoding)",
)
def cidades(
    nome: str = Query(..., min_length=1, description="Nome da cidade, ex.: 'Aracaju'."),
    limite: int = Query(5, ge=1, le=20, description="Máximo de resultados."),
) -> list[Cidade]:
    """Resolve nome de cidade em coordenadas — use para o autocomplete do front."""
    try:
        return buscar_cidade(nome, limite)
    except Exception as exc:  # rede/HTTP
        raise HTTPException(
            status_code=502, detail=f"Falha na busca de cidade: {exc}"
        ) from exc


@app.get(
    "/previsao",
    response_model=Previsao,
    tags=["tempo"],
    summary="Previsão crua (dados de tempo)",
)
def previsao(
    lat: float = Query(..., ge=-90, le=90, description="Latitude em graus decimais."),
    lon: float = Query(..., ge=-180, le=180, description="Longitude em graus decimais."),
) -> Previsao:
    """Dados climáticos da Open-Meteo: atual, 7 dias e séries horárias."""
    return _previsao_cacheada(lat, lon)


@app.get(
    "/recomendacao",
    response_model=RecomendacaoCompleta,
    tags=["ia"],
    summary="Vereditos + recomendação (tratado com IA)",
)
def recomendacao(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
) -> RecomendacaoCompleta:
    """Aplica as regras agronômicas e gera o resumo da IA (com fallback offline)."""
    previsao = _previsao_cacheada(lat, lon)
    vereditos = avaliar_previsao(previsao)
    texto, usou_llm = gerar_recomendacao_segura(vereditos, previsao)
    return RecomendacaoCompleta(
        vereditos={t: VereditoOut(**v.to_dict()) for t, v in vereditos.items()},
        recomendacao=RecomendacaoOut(texto=texto, usou_llm=usou_llm),
    )


@app.get(
    "/clima",
    response_model=ClimaCompleto,
    tags=["ia"],
    summary="Tudo em uma chamada (previsão + vereditos + IA)",
)
def clima(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
) -> ClimaCompleto:
    """Payload completo para o front montar a tela 'Clima do dia' de uma vez."""
    previsao = _previsao_cacheada(lat, lon)
    vereditos = avaliar_previsao(previsao)
    texto, usou_llm = gerar_recomendacao_segura(vereditos, previsao)
    return ClimaCompleto(
        previsao=previsao,
        vereditos={t: VereditoOut(**v.to_dict()) for t, v in vereditos.items()},
        recomendacao=RecomendacaoOut(texto=texto, usou_llm=usou_llm),
    )
