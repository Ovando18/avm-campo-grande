# AVM Campo Grande/MS — Avaliação Automatizada de Imóveis

Aplicação web (Streamlit) que estima o **valor de mercado de imóveis residenciais em Campo Grande/MS** pelo
método comparativo direto de dados de mercado, usando a **regra da mediana homogeneizada**, e emite um
**Parecer Técnico em PDF** (A4) com os dados do solicitante. A metodologia se inspira na ABNT NBR 14653.

## Funcionalidades

| Etapa | O que faz |
|---|---|
| **1 · Imóvel** | 73 bairros oficiais de Campo Grande, mais loteamentos conhecidos (ex.: *Carandá Bosque*), com busca e opção "Outro/Condomínio". CEP opcional validado pelo ViaCEP (precisa ser de Campo Grande/MS). Tipo do imóvel, testada × profundidade com área calculada na hora (pode ser ajustada para terreno irregular), área construída, quartos, banheiros, vagas e melhorias. |
| **2 · Solicitante** | Nome, CPF (com dígitos verificadores), telefone/WhatsApp (DDD válido), e-mail e aceite da LGPD. |
| **3 · Resultado** | Valor estimado (mediana homogeneizada), faixa de ±10%, R$/m² construído e de terreno, memória de cálculo, tabela das amostras com link de origem, outliers removidos e o botão **Baixar Laudo (.PDF)**. |

## Motor de avaliação (`avm/engine.py`)

1. **Coleta online**: VivaReal e ZAP (API de busca *glue-api*) e OLX (`__NEXT_DATA__`), filtrando por
   Campo Grande/MS, bairro e tipo. Anúncios repetidos entre portais são removidos.
2. **Similaridade**: área construída **±30%** e quartos **±1**.
3. **Fallback geográfico**: se houver **menos de 5 amostras válidas**, a pesquisa se amplia nesta ordem:
   bairro → Região Urbana (Centro, Segredo, Prosa, Bandeira, Anhanduizinho, Lagoa, Imbirussu) →
   regiões adjacentes → município inteiro.
4. **Saneamento IQR**: o R$/m² precisa ficar em `[Q1 − 1,5·IQR ; Q3 + 1,5·IQR]`. Isso descarta leilões e erros de digitação.
5. `V_base = Mediana(R$/m²) × Área construída`.
6. **Fator terreno**: `(A_terreno / mediana dos terrenos da amostra)^0,25`, limitado a 0,85–1,15.
   Só entra quando a diferença passa de 20% e nunca para apartamentos.
7. **Melhorias** (teto de +25%): piscina 6%, gourmet 4%, armários 4%, energia solar 4%, alto padrão 5%,
   segurança 2%, edícula 3%*.
8. `Valor_Final = V_base × Fator_Terreno × (1 + Σ Melhorias)`, com faixa de ±10%.

\* A especificação original não define percentual para edícula. Foi adotado +3%; ajuste em `avm/models.py`.

As constantes técnicas ficam no topo de `avm/engine.py` e em `avm/models.py`.

## Coleta, cache e modo simulado

- **Cache SQLite** por fonte, bairro e tipo, com validade (TTL) de 7 dias (`CACHE_TTL_DAYS`). Evita bloqueios e acelera consultas repetidas.
- **Proxy anti-bloqueio** opcional: `SCRAPER_PROVIDER=zenrows` ou `scraperapi`, com a chave correspondente.
- **Mock inteligente**: só entra quando **todas** as fontes falham (offline ou bloqueadas) e `AVM_ALLOW_MOCK=true`.
  Gera amostras determinísticas e plausíveis por bairro, incluindo outliers propositais.
  A tela e o PDF ficam **marcados como "MODO DEMONSTRAÇÃO"**.
  Em produção, use `AVM_ALLOW_MOCK=false` para mostrar um erro em vez de simular.

> ⚠️ Portais imobiliários mudam endpoints e aplicam anti-bot com frequência. Os coletores em `avm/scraper.py`
> funcionam por melhor esforço. Em produção, use um serviço de proxy e verifique os Termos de Uso de cada portal.

## Rodando localmente

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # edite os dados da empresa
streamlit run streamlit_app.py
```

Para testar sem acesso à internet: `AVM_FORCE_MOCK=true streamlit run streamlit_app.py`.

Testes: `pytest -q`

## Publicando no Streamlit Community Cloud

1. Entre em <https://share.streamlit.io> com a sua conta do GitHub.
2. **Create app → Deploy a public app from GitHub**. Selecione este repositório, branch `main` e arquivo `streamlit_app.py`.
3. Em **Advanced settings → Secrets**, cole as variáveis do `.env.example` em formato TOML, por exemplo:
   ```toml
   COMPANY_NAME = "Minha Empresa de Avaliações Ltda."
   COMPANY_CNPJ = "12.345.678/0001-90"
   AVM_ALLOW_MOCK = "true"
   ```
4. **Deploy**. Para usar o logotipo, coloque o arquivo em `assets/logo.png` no repositório.

## Estrutura

```
streamlit_app.py            # interface (wizard em 3 etapas)
avm/
  config.py                 # configurações (.env / st.secrets)
  bairros.py                # bairros, regiões, aliases e fallback geográfico
  validators.py             # CPF, telefone, e-mail, CEP
  cep.py                    # ViaCEP + validação por faixa postal de Campo Grande
  scraper.py                # VivaReal, ZAP, OLX (+ ZenRows/ScraperAPI)
  collector.py              # cache → online → mock
  cache.py                  # cache SQLite com TTL
  mock.py                   # amostras simuladas (modo demonstração)
  engine.py                 # mediana homogeneizada, IQR e fatores
  pdf_report.py             # laudo PDF A4 (ReportLab)
data/bairros_campo_grande.json   # bairros oficiais por Região Urbana + adjacências
tests/test_engine.py
```

## Por que Streamlit em vez de Next.js

O Streamlit Community Cloud executa apenas Python. Por isso a interface usa Streamlit,
a estatística usa Pandas/NumPy e o PDF usa ReportLab, tudo em um único serviço.
O pacote `avm/` não depende do Streamlit e pode ser exposto via FastAPI no futuro, caso se queira um front-end Next.js.

## Aviso

Trata-se de uma estimativa estatística baseada em ofertas online. **Não substitui** laudo com vistoria presencial
feito por profissional habilitado (NBR 14653) para fins judiciais ou garantias bancárias. A lista de bairros segue a
divisão em Regiões Urbanas da PLANURB; confira periodicamente com a publicação oficial mais recente.
