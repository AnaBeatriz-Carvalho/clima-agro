# clima-agro · API

API REST que disponibiliza recomendações agrícolas a partir de dados meteorológicos
da [Open-Meteo](https://open-meteo.com/). Responde, para o produtor rural:

- Vai chover? Quanto (mm)?
- É um bom momento para pulverizar?
- Preciso irrigar?
- Há risco de geada?

> **Esta branch (`api`) contém apenas o backend/API.** O front-end é desenvolvido
> separadamente e consome estes endpoints. A interface Streamlit vive na branch `main`.

## Arquitetura

```
Dados (Open-Meteo) → Regras determinísticas (Python) → LLM (apenas tradução) → API REST (FastAPI)
```

Todo cálculo e decisão numérica acontece em Python, de forma testável. A LLM apenas
traduz os vereditos já calculados para uma mensagem clara em português — **nunca
recalcula nem inventa números**. Se a IA estiver indisponível (sem chave, offline ou
cota excedida), a API cai em um **texto determinístico** gerado pelas próprias regras:
nunca fica sem resposta.

## Estrutura

| Arquivo | Papel |
|---|---|
| `api.py` | **API REST (FastAPI)** — endpoints HTTP/JSON |
| `config.py` | localização, variáveis da Open-Meteo, thresholds, config da LLM |
| `weather_service.py` | consumo da Open-Meteo + validação com pydantic |
| `rules_service.py` | camada de regras determinísticas (vereditos) |
| `ai_service.py` | IA: Gemini (nuvem) ou LM Studio (local) + fallback offline |
| `tests/test_rules.py` | testes das regras (pytest, offline) |

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Configure a chave da IA (opcional, mas recomendado — sem ela a API responde com o
texto determinístico): copie `.env.example` para `.env` e preencha `GEMINI_API_KEY`.

## Rodar a API

```powershell
uvicorn api:app --reload                       # desenvolvimento (localhost:8000)
uvicorn api:app --host 0.0.0.0 --port 8000     # acessível na rede
```

- **Docs interativas (Swagger):** <http://localhost:8000/docs>
- **Docs alternativas (ReDoc):** <http://localhost:8000/redoc>

O front-end roda em outra origem, então o **CORS está liberado** (em produção,
restrinja `allow_origins` ao domínio real do front em `api.py`).

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/saude` | health check + provedor de IA ativo |
| `GET` | `/cidades?nome=&limite=` | busca cidades por nome (geocoding) — para autocomplete |
| `GET` | `/previsao?lat=&lon=` | dados de tempo crus (atual + 7 dias + séries horárias) |
| `GET` | `/recomendacao?lat=&lon=` | vereditos + resumo da IA (tratado com IA) |
| `GET` | `/clima?lat=&lon=` | **tudo em uma chamada** (previsão + vereditos + IA) |

**Fluxo típico do front:** `/cidades?nome=...` (autocomplete) → escolhe a cidade e
pega `latitude`/`longitude` → `/clima?lat=&lon=` para montar a tela inteira.

Para reduzir chamadas externas (limites da Open-Meteo e cota da Gemini), a API mantém
um **cache em memória com TTL de 30 minutos** por coordenada.

### Exemplos

```bash
# Health check
curl "http://localhost:8000/saude"
# {"status":"ok","provedor_llm":"gemini"}

# Buscar cidade
curl "http://localhost:8000/cidades?nome=Aracaju&limite=1"

# Tudo em uma chamada
curl "http://localhost:8000/clima?lat=-10.9111&lon=-37.0717"
```

### Formato da resposta de `/clima`

```jsonc
{
  "previsao": {
    "latitude": -10.91, "longitude": -37.07, "timezone": "America/Sao_Paulo",
    "current": { "temperature_2m": 25.0, "relative_humidity_2m": 80, "...": "..." },
    "daily":   { "time": ["2026-06-10", "..."], "precipitation_sum": [0.9, "..."], "...": "..." },
    "hourly":  { "...": "..." }
  },
  "vereditos": {
    "pulverizacao": { "status": "nao_recomendado", "motivo": "...", "dados_de_apoio": { "...": "..." } },
    "irrigacao":    { "status": "sugerida",        "motivo": "...", "dados_de_apoio": { "...": "..." } },
    "geada":        { "status": "sem_risco",       "motivo": "...", "dados_de_apoio": { "...": "..." } },
    "chuva_forte":  { "status": "normal",          "motivo": "...", "dados_de_apoio": { "...": "..." } }
  },
  "recomendacao": {
    "texto": "Hoje teremos chuvas leves...",
    "usou_llm": true                // false => veio do fallback determinístico (IA offline/cota)
  }
}
```

## Camada de IA

A API suporta dois provedores, escolhidos por `LLM_PROVIDER`:

| Provedor | Quando usar | Configuração |
|---|---|---|
| **Gemini** (nuvem) | produção / deploy | `GEMINI_API_KEY` (variável de ambiente) |
| **LM Studio** (local) | desenvolvimento sem custo | servidor em `localhost:1234` |

No modo padrão (`LLM_PROVIDER=auto`): usa **Gemini se houver chave**, senão o
**LM Studio local**, senão o **texto determinístico** das regras.

**Gemini:**

1. Crie uma chave em <https://aistudio.google.com/apikey>.
2. Preencha `GEMINI_API_KEY` no `.env`.
3. Modelo padrão recomendado para free-tier: `gemini-flash-lite-latest` (cota grátis
   maior, menos `429`). Ajuste com `GEMINI_MODELO`. A cota é **por modelo**; se um
   estourar, troque por outro lite (ex.: `gemini-2.5-flash-lite`). Modelos **Pro**
   exigem billing. Detalhes em `HANDOFF.md`.

## Testes

```powershell
pytest                      # testes das regras determinísticas (offline)
python weather_service.py   # teste manual: previsão dos próximos dias
python rules_service.py     # teste manual: vereditos das regras
python ai_service.py        # teste manual: resumo em PT-BR (com fallback)
```

## Configuração

Ajuste `config.py`:

- **Localização padrão**: `LATITUDE_PADRAO` / `LONGITUDE_PADRAO` (padrão: Aracaju/SE).
- **Thresholds agronômicos**: classe `Thresholds`. São pontos de partida — revisar
  com fonte técnica (Embrapa, etc.) antes de uso real.
- **LM Studio**: `LM_STUDIO_URL` (servidor OpenAI-compatible em `localhost:1234`).
