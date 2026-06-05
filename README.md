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
| `ai_service.py` | IA: Gemini (nuvem) ou LM Studio (local) + fallback | 3 ✅ |
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

### Camada de IA (resumo em linguagem natural)

O sistema suporta dois provedores, escolhidos por `LLM_PROVIDER`:

| Provedor | Quando usar | Configuração |
|---|---|---|
| **Gemini** (nuvem) | publicação / deploy | `GEMINI_API_KEY` (env ou `st.secrets`) |
| **LM Studio** (local) | desenvolvimento sem custo | servidor em `localhost:1234` |

No modo padrão (`LLM_PROVIDER=auto`): usa **Gemini se houver chave**, senão o
**LM Studio local**, senão um **texto determinístico** gerado pelas próprias
regras. Ou seja, **o sistema nunca fica sem resposta** — e nenhum segredo fica no
código.

**Gemini (recomendado para deploy):**

1. Crie uma chave em <https://aistudio.google.com/apikey> (free tier suficiente).
2. Local: copie `.env.example` para `.env` e preencha `GEMINI_API_KEY`
   (ou exporte a variável no terminal).
3. Modelo padrão: `gemini-2.5-flash` (leve/barato). Ajuste com `GEMINI_MODELO`.

**LM Studio (local):** rode um modelo (ex.: Llama 3.1 8B Instruct ou Qwen 2.5 7B)
com o servidor local ativo em `localhost:1234`.

### Deploy (Streamlit Community Cloud)

1. Suba o repositório no GitHub (o `.env` e `secrets.toml` ficam de fora pelo
   `.gitignore`).
2. Em <https://share.streamlit.io>, aponte para `app.py`.
3. Em **Settings → Secrets**, cole sua chave (veja
   `.streamlit/secrets.toml.example`):
   ```toml
   GEMINI_API_KEY = "sua-chave"
   ```
   O `app.py` faz a ponte de `st.secrets` para as variáveis de ambiente.

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
