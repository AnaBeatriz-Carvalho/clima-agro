"""Camada LLM — tradução dos vereditos para linguagem do produtor.

Conecta ao LM Studio (servidor OpenAI-compatible local). A LLM **não** calcula
nem decide nada: recebe (a) um resumo dos dados climáticos e (b) os vereditos já
calculados por `rules_service.py`, e escreve uma mensagem curta e prática em PT-BR.

Se o LM Studio estiver indisponível, `recomendacao_fallback` gera um texto
determinístico a partir dos próprios vereditos — o sistema nunca fica sem resposta.
"""

from __future__ import annotations

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
    "- Este é apenas um site informativo. NÃO peça para a pessoa entrar em contato, "
    "NÃO mande 'falar conosco', NÃO ofereça suporte nem prometa ajuda.\n"
    "- NÃO mande tomar providências genéricas ('procure um técnico', 'tome outras "
    "medidas'). Apenas informe o que o tempo diz e o que isso significa na prática.\n"
    "- NÃO assine, NÃO se despeça formalmente, NÃO use '[Seu nome]'.\n"
    "- Comece direto pela informação mais importante (vai chover ou não, e quanto)."
)


class LMStudioIndisponivel(RuntimeError):
    """Erro de conexão/timeout/HTTP ao falar com o LM Studio."""


# --------------------------------------------------------------------------- #
# Preparação dos dados para a LLM
# --------------------------------------------------------------------------- #


def resumir_clima(previsao: Previsao, dias: int = 3) -> dict[str, object]:
    """Monta um resumo compacto do clima para a LLM (sem expor o JSON inteiro)."""
    d = previsao.daily
    atual = previsao.current
    return {
        "agora": {
            "temperatura_c": atual.temperature_2m,
            "umidade_pct": atual.relative_humidity_2m,
            "chuva_mm": atual.precipitation,
            "vento_kmh": atual.wind_speed_10m,
        },
        "proximos_dias": [
            {
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


def gerar_recomendacao(
    vereditos: dict[str, Veredito],
    previsao: Previsao,
) -> str:
    """Gera o texto final via LM Studio.

    Raises:
        LMStudioIndisponivel: se o servidor não responder ou retornar erro.
    """
    payload = {
        "model": config.LM_STUDIO_MODELO,
        "temperature": config.LM_STUDIO_TEMPERATURA,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _montar_mensagem_usuario(
                    vereditos, resumir_clima(previsao)
                ),
            },
        ],
    }
    try:
        resposta = requests.post(
            config.LM_STUDIO_URL,
            json=payload,
            timeout=config.TIMEOUT_HTTP,
        )
        resposta.raise_for_status()
    except requests.RequestException as exc:
        raise LMStudioIndisponivel(
            f"Não foi possível falar com o LM Studio em {config.LM_STUDIO_URL}: {exc}"
        ) from exc

    dados = resposta.json()
    return dados["choices"][0]["message"]["content"].strip()


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
    except LMStudioIndisponivel:
        return recomendacao_fallback(vereditos), False


if __name__ == "__main__":
    # Teste manual: busca previsão real, calcula vereditos e pede o texto.
    from rules_service import avaliar_previsao
    from weather_service import buscar_previsao

    prev = buscar_previsao()
    vers = avaliar_previsao(prev)
    texto, usou_llm = gerar_recomendacao_segura(vers, prev)
    print(f"[{'LM Studio' if usou_llm else 'fallback'}]\n")
    print(texto)
