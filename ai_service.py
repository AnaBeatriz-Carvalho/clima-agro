"""Camada LLM — tradução dos vereditos para linguagem do produtor.

Suporta dois provedores (escolhidos em `config.provedor_llm()`):
- **Gemini** (Google) — para o projeto publicado na nuvem. Chave via env
  `GEMINI_API_KEY` (nunca no código).
- **LM Studio** — servidor local OpenAI-compatible, para desenvolvimento.

A LLM **não** calcula nem decide nada: recebe (a) um resumo dos dados climáticos
e (b) os vereditos já calculados por `rules_service.py`, e escreve uma mensagem
curta e prática em PT-BR.

Se a LLM estiver indisponível (sem chave, servidor offline, erro), o sistema cai
em `recomendacao_fallback` — um texto determinístico a partir dos próprios
vereditos. Nunca fica sem resposta.
"""

from __future__ import annotations

from datetime import date, datetime

import requests

import config
from rules_service import Veredito
from weather_service import Previsao


SYSTEM_PROMPT = (
    "Você é um assistente que explica previsões do tempo para produtores rurais "
    "brasileiros. Receba os dados meteorológicos e as recomendações já calculadas "
    "e escreva um resumo curto (no máximo 4 ou 5 frases), claro e em português "
    "simples, como se conversasse com a pessoa.\n"
    "REGRAS:\n"
    "- NÃO invente números. NÃO recalcule. Use SOMENTE os números fornecidos.\n"
    "- Para se referir aos dias, use EXATAMENTE o rótulo no campo 'quando' de cada "
    "dia (Hoje, Amanhã, Sábado, etc.). NÃO calcule datas nem dias da semana por "
    "conta própria — você não sabe o calendário, então confie apenas no rótulo dado.\n"
    "- Este é apenas um site informativo. NÃO peça para a pessoa entrar em contato, "
    "NÃO mande 'falar conosco', NÃO ofereça suporte nem prometa ajuda.\n"
    "- NÃO mande tomar providências genéricas ('procure um técnico', 'tome outras "
    "medidas'). Apenas informe o que o tempo diz e o que isso significa na prática.\n"
    "- NÃO assine, NÃO se despeça formalmente, NÃO use '[Seu nome]'.\n"
    "- Comece direto pela informação mais importante (vai chover ou não, e quanto)."
)

_DIAS_SEMANA = [
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
]


def _rotulo_dia(iso: str) -> str:
    """Rótulo determinístico do dia ('Hoje', 'Amanhã' ou dia da semana).

    A LLM não sabe a data de hoje e erra ao deduzir 'hoje/amanhã' de uma data ISO;
    por isso o cálculo é feito aqui e entregue pronto.
    """
    try:
        d = datetime.strptime(iso, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return iso
    delta = (d - date.today()).days
    if delta == 0:
        return "Hoje"
    if delta == 1:
        return "Amanhã"
    return _DIAS_SEMANA[d.weekday()].capitalize()


class LLMIndisponivel(RuntimeError):
    """Erro ao falar com a LLM (sem chave, offline, timeout, HTTP ou resposta vazia)."""


# --------------------------------------------------------------------------- #
# Preparação dos dados para a LLM
# --------------------------------------------------------------------------- #


def resumir_clima(previsao: Previsao, dias: int = 3) -> dict[str, object]:
    """Monta um resumo compacto do clima para a LLM (sem expor o JSON inteiro)."""
    d = previsao.daily
    atual = previsao.current
    return {
        "data_de_hoje": date.today().isoformat(),
        "agora": {
            "temperatura_c": atual.temperature_2m,
            "umidade_pct": atual.relative_humidity_2m,
            "chuva_mm": atual.precipitation,
            "vento_kmh": atual.wind_speed_10m,
        },
        "proximos_dias": [
            {
                "quando": _rotulo_dia(d.time[i]),
                "dia": d.time[i],
                "chuva_mm": d.precipitation_sum[i],
                "prob_chuva_pct": d.precipitation_probability_max[i],
                "temp_min_c": d.temperature_2m_min[i],
                "temp_max_c": d.temperature_2m_max[i],
            }
            for i in range(min(dias, len(d.time)))
        ],
    }


def _montar_mensagem_usuario(
    vereditos: dict[str, Veredito],
    resumo: dict[str, object],
) -> str:
    """Texto enviado como mensagem 'user' à LLM: resumo + vereditos."""
    linhas = ["Dados meteorológicos (resumo):", str(resumo), "", "Recomendações já calculadas:"]
    for tema, v in vereditos.items():
        linhas.append(f"- {tema}: {v.status} — {v.motivo}")
    linhas.append(
        "\nEscreva uma mensagem curta para o produtor reunindo essas informações."
    )
    return "\n".join(linhas)


# --------------------------------------------------------------------------- #
# Chamada à LLM
# --------------------------------------------------------------------------- #


def _chamar_gemini(system: str, usuario: str) -> str:
    """Chama a API REST da Gemini (generateContent). Raises LLMIndisponivel."""
    api_key = config.gemini_api_key()
    if not api_key:
        raise LLMIndisponivel("GEMINI_API_KEY não definida.")

    url = f"{config.GEMINI_BASE_URL}/{config.gemini_modelo()}:generateContent"
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": usuario}]}],
        "generationConfig": {"temperature": config.LLM_TEMPERATURA},
    }
    try:
        resposta = requests.post(
            url,
            params={"key": api_key},
            json=payload,
            timeout=config.TIMEOUT_HTTP,
        )
        resposta.raise_for_status()
    except requests.RequestException as exc:
        raise LLMIndisponivel(f"Falha ao chamar a Gemini: {exc}") from exc

    dados = resposta.json()
    try:
        return dados["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError) as exc:
        # Sem candidatos (ex.: conteúdo bloqueado por filtro de segurança).
        raise LLMIndisponivel(f"Resposta vazia da Gemini: {dados}") from exc


def _chamar_lmstudio(system: str, usuario: str) -> str:
    """Chama o LM Studio (OpenAI-compatible). Raises LLMIndisponivel."""
    payload = {
        "model": config.LM_STUDIO_MODELO,
        "temperature": config.LLM_TEMPERATURA,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": usuario},
        ],
    }
    try:
        resposta = requests.post(
            config.LM_STUDIO_URL, json=payload, timeout=config.TIMEOUT_HTTP
        )
        resposta.raise_for_status()
    except requests.RequestException as exc:
        raise LLMIndisponivel(
            f"Não foi possível falar com o LM Studio em {config.LM_STUDIO_URL}: {exc}"
        ) from exc

    return resposta.json()["choices"][0]["message"]["content"].strip()


def gerar_recomendacao(
    vereditos: dict[str, Veredito],
    previsao: Previsao,
) -> str:
    """Gera o texto final usando o provedor configurado (Gemini ou LM Studio).

    Raises:
        LLMIndisponivel: se o provedor não responder ou retornar erro.
    """
    usuario = _montar_mensagem_usuario(vereditos, resumir_clima(previsao))
    if config.provedor_llm() == "gemini":
        return _chamar_gemini(SYSTEM_PROMPT, usuario)
    return _chamar_lmstudio(SYSTEM_PROMPT, usuario)


def recomendacao_fallback(vereditos: dict[str, Veredito]) -> str:
    """Texto determinístico a partir dos vereditos (quando a LLM está offline)."""
    titulos = {
        "pulverizacao": "Pulverização",
        "irrigacao": "Irrigação",
        "geada": "Geada",
        "chuva_forte": "Chuva forte",
    }
    linhas = ["Recomendações (modo offline, sem IA):", ""]
    for tema, v in vereditos.items():
        linhas.append(f"• {titulos.get(tema, tema)}: {v.motivo}")
    return "\n".join(linhas)


def gerar_recomendacao_segura(
    vereditos: dict[str, Veredito],
    previsao: Previsao,
) -> tuple[str, bool]:
    """Tenta a LLM; cai no fallback determinístico se ela estiver indisponível.

    Returns:
        (texto, usou_llm). `usou_llm=False` indica que veio do fallback.
    """
    try:
        return gerar_recomendacao(vereditos, previsao), True
    except LLMIndisponivel:
        return recomendacao_fallback(vereditos), False


if __name__ == "__main__":
    # Teste manual: busca previsão real, calcula vereditos e pede o texto.
    from rules_service import avaliar_previsao
    from weather_service import buscar_previsao

    prev = buscar_previsao()
    vers = avaliar_previsao(prev)
    texto, usou_llm = gerar_recomendacao_segura(vers, prev)
    fonte = config.provedor_llm() if usou_llm else "fallback determinístico"
    print(f"[provedor: {fonte}]\n")
    print(texto)
