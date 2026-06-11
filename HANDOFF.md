# Handoff — Clima Agro

Documento de passagem de contexto: estado atual do projeto, decisões recentes e
pontos de atenção para quem (pessoa ou agente) continuar o trabalho.

_Última atualização: 2026-06-10._

## O que é

App Streamlit que dá recomendações agrícolas em linguagem simples a partir da
previsão do tempo (Open-Meteo). Arquitetura em camadas, com a IA atuando **apenas
como tradutora** dos vereditos já calculados em Python — nunca recalcula nem inventa
números. Visão geral e setup estão no `README.md`.

```
Dados (Open-Meteo) → Regras determinísticas (Python) → LLM (só tradução) → UI (ui.py)
```

## Estado atual

| Camada | Arquivo | Situação |
|---|---|---|
| Dados | `weather_service.py` | estável |
| Regras | `rules_service.py` (+ `tests/`) | estável, 18 testes passando |
| IA | `ai_service.py` | Gemini (nuvem) ou LM Studio (local) + fallback offline |
| Gráficos | `charts.py` | Plotly (chuva e temperatura) |
| Visual | `ui.py` | **novo** — CSS + blocos HTML, tema claro/escuro |
| Orquestração | `app.py` | monta a página chamando `ui.bloco_*` |

## Mudanças recentes (esta sessão)

1. **Redesign da interface — Direção C "Clima do dia"** (a partir do wireframe feito
   no Claude Design). Estética desenhada à mão (fonte Patrick Hand, bordas irregulares
   `.sk`, azul-clima), **semáforo de cor nos vereditos** (verde = ok, âmbar = atenção,
   vermelho = evite), emojis mantidos, **tema claro/escuro** com toggle na sidebar.
   - Toda a apresentação foi extraída para **`ui.py`**: `injetar_css(tema)` injeta o
     tema escolhido + CSS base; os `bloco_*(...)` devolvem strings HTML para
     `st.markdown(..., unsafe_allow_html=True)`.
   - Ordem da página: título → herói (tempo agora) → recomendações (chips + cards) →
     resumo da IA → 7 dias → gráficos (em expander).
   - **Armadilha conhecida (resolvida):** o markdown do Streamlit trata linha indentada
     com 4+ espaços como bloco de código e mostra o HTML cru. Por isso `ui._clean()`
     colapsa cada bloco em uma linha sem indentação **antes** de enviar. Qualquer novo
     `bloco_*` deve passar por `_clean()`.
   - Como o Streamlit não conhece o toggle, `ui.py` força cor de texto/borda dos widgets
     (sidebar, inputs, botão) nos dois temas via CSS.

2. **Contagem de dias errada (alucinação) — corrigida na fonte.** A LLM recebia só datas
   ISO e tentava deduzir "hoje/amanhã" sem saber o calendário, errando. Agora
   `ai_service.resumir_clima` envia um rótulo determinístico por dia (`_rotulo_dia` →
   "Hoje"/"Amanhã"/dia da semana) + a data de hoje, e o `SYSTEM_PROMPT` proíbe a LLM de
   calcular datas. **Mantenha essa regra** se mexer no prompt.

3. **Modelo Gemini → `gemini-flash-latest`** (padrão em `config.gemini_modelo()` e no
   `.env`). Ver "Pontos de atenção".

4. **Deprecação corrigida:** `st.plotly_chart(..., use_container_width=True)` →
   `width="stretch"` em `app.py`.

5. **Robustez da LLM + diagnóstico do 429 (branch `developer`).** O sintoma "1ª busca
   mostra IA offline, 2ª funciona" era **cota do free-tier (429)**, não cold-start. Em
   `ai_service.py`:
   - O motivo do erro agora vai pro log (antes era engolido em silêncio) — foi ele que
     revelou o 429.
   - **Retry curto** (2 tentativas) só para falhas de conexão/timeout/5xx. O **429 de
     cota cai no fallback offline na hora** — retry não ajuda (cota não reseta em
     segundos) e só fazia o usuário esperar ~44s.
   - **Modelo recomendado para free-tier → `gemini-flash-lite-latest`** (no `.env` e
     `.env.example`). Os modelos "lite" têm cota grátis maior; a cota é **por modelo**,
     então um lite "novo" tem cota fresca.

## Pontos de atenção

- **Cota do free-tier (429).** Mesmo nos modelos flash, o free-tier tem limite de
  requisições e retorna **429 (cota excedida)** quando estoura — o app então cai no texto
  offline (na hora, ver mudança 5). A cota é **por modelo**: prefira `gemini-flash-lite-latest`
  (cota grátis maior) e, se estourar, troque por outro lite (`gemini-2.5-flash-lite`).
  Para acabar de vez com o 429, ative **billing** no Google AI Studio.
- **Modelos Pro exigem billing.** `gemini-2.5-pro` e `gemini-3-pro-preview` retornam
  **429** no free-tier. Para usá-los, ative billing e troque `GEMINI_MODELO`.
- **Segredos:** `.env` (com `GEMINI_API_KEY`) está no `.gitignore` — não versionar. Em
  deploy (Streamlit Cloud), usar **Settings → Secrets**; `app.py` faz a ponte de
  `st.secrets` para variáveis de ambiente.
- **Thresholds agronômicos** (`config.Thresholds`) são pontos de partida — revisar com
  fonte técnica (Embrapa) antes de uso real.

## Como rodar / verificar

```powershell
streamlit run app.py     # interface completa
python ai_service.py     # testa previsão + resumo da IA (com fallback)
pytest                   # 18 testes das regras (offline)
```

Checklist de verificação visual (no navegador): herói com temperatura grande, chips
coloridos, cards com semáforo, resumo da IA, 7 cartões de dias; alternar tema
claro/escuro na sidebar; estreitar a janela (~400px) para conferir o reflow.

## Próximos passos sugeridos

- [ ] Histórico de 30 dias.
- [ ] Deploy no Streamlit Community Cloud.
- [ ] (Opcional) Se ativar billing, avaliar `gemini-2.5-pro`/`gemini-3-pro-preview`
      para o resumo.
