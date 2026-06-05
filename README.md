# clima-agro

Recomendações agrícolas em linguagem simples a partir de dados meteorológicos da
[Open-Meteo](https://open-meteo.com/). O sistema responde, para o produtor rural:

- Vai chover? Quanto (mm)?
- É um bom momento para pulverizar?
- Preciso irrigar?
- Há risco de geada?

## Arquitetura

```
Dados (Open-Meteo) → Regras determinísticas (Python) → LLM (apenas tradução)
```

Todo cálculo e decisão numérica acontece em Python, de forma testável. A LLM
(local, via LM Studio) apenas traduz os vereditos já calculados para uma mensagem
clara em português — **nunca recalcula nem inventa números**.

## Estrutura

| Arquivo | Papel | Fase |
|---|---|---|
| `config.py` | localização, variáveis da API, thresholds, endpoint LLM | 1 |
| `weather_service.py` | consumo da Open-Meteo + validação com pydantic | 1 ✅ |
| `rules_service.py` | camada de regras determinísticas (vereditos) | 2 ✅ |
| `tests/test_rules.py` | testes das regras (pytest) | 2 ✅ |
| `ai_service.py` | integração com LM Studio (+ fallback offline) | 3 ✅ |
| `charts.py` | gráficos Plotly (chuva e temperatura) | 4 ✅ |
| `app.py` | interface Streamlit | 4 ✅ |

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Uso

Interface completa (recomendado):

```powershell
streamlit run app.py
```

Busca por cidade ou coordenadas, condições atuais, vereditos, resumo da LLM e
gráficos de chuva/temperatura.

Scripts de linha de comando (teste manual de cada camada):

```powershell
python weather_service.py   # previsão dos próximos dias
python rules_service.py     # vereditos das regras
python ai_service.py        # resumo em PT-BR (LM Studio, com fallback)
pytest                      # testes das regras (offline)
```

### LM Studio (opcional)

Para o resumo em linguagem natural, rode um modelo no
[LM Studio](https://lmstudio.ai/) com o servidor local ativo em
`localhost:1234` (modelo sugerido: Llama 3.1 8B Instruct ou Qwen 2.5 7B).
**Sem o LM Studio o sistema continua funcionando** — o resumo cai num texto
determinístico gerado pelas próprias regras.

## Configuração

Ajuste `config.py`:

- **Localização**: `LATITUDE_PADRAO` / `LONGITUDE_PADRAO` (padrão: Aracaju/SE).
- **Thresholds agronômicos**: classe `Thresholds`. São pontos de partida —
  revisar com fonte técnica (Embrapa, etc.) antes de uso real.
- **LLM**: `LM_STUDIO_URL` (servidor OpenAI-compatible em `localhost:1234`).

## Roadmap

- [x] Fase 1 — núcleo de dados (`weather_service.py` + pydantic)
- [x] Fase 2 — regras determinísticas + testes
- [x] Fase 3 — LLM (`ai_service.py` via LM Studio + fallback offline)
- [x] Fase 4 — interface (Streamlit + Plotly)
- [x] Fase 5 — geocoding por nome de cidade (`buscar_cidade`)
- [ ] Fase 5 (extra) — histórico de 30 dias, deploy
