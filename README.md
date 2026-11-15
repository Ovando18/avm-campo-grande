# AVM Campo Grande/MS — Avaliação Automatizada de Imóveis

Aplicação web (Streamlit) que estima o **valor de mercado de imóveis residenciais em Campo Grande/MS** pelo
método comparativo direto de dados de mercado, usando a **regra da mediana homogeneizada**, e emite um
**Parecer Técnico em PDF** (A4) com os dados do solicitante. A metodologia se inspira na ABNT NBR 14653.

## Funcionalidades

| Etapa | O que faz |
|---|---|
| **1 · Imóvel** | Bairro com busca: bairros oficiais e nomes usados pelos portais (ex.: *Água Limpa Park*, *Carandá Bosque*). **Qualquer bairro pode ser digitado**, com ou sem acento ("agua limpa" → Água Limpa Park). **Bairros vizinhos** (usados só se faltar amostra no bairro). CEP opcional validado pelo ViaCEP. Tipo, **padrão construtivo** (Baixo / Normal / Alto), testada × profundidade com área calculada na hora, área construída, quartos, banheiros, vagas e melhorias. |
| **2 · Solicitante** | Nome, CPF (com dígitos verificadores), telefone/WhatsApp (DDD válido), e-mail e aceite da LGPD. |
| **3 · Resultado** | Valor estimado (mediana homogeneizada), faixa de ±10%, R$/m² construído e de terreno, memória de cálculo, tabela das amostras com link de origem, outliers removidos e o botão **Baixar Laudo (.PDF)**. |

## Motor de avaliação (`avm/engine.py`)

1. **Coleta online**: Infoimóveis, VivaReal e ZAP (API de busca *glue-api*) e OLX (`__NEXT_DATA__`),
   filtrando por Campo Grande/MS, bairro e tipo. Anúncios repetidos entre portais são removidos.
2. **Mesmo padrão**: mesmo tipo, mesmo **padrão construtivo** (identificado por palavras-chave do anúncio;
   anúncios sem informação são mantidos e tratados pelo saneamento), área construída **±30%**,
   quartos **±1** e banheiros **±1**.
3. **Mesmo bairro primeiro**: a avaliação usa só imóveis do **mesmo bairro**. **Somente se** houver menos de
   5 amostras válidas, a pesquisa inclui os **bairros vizinhos informados**. Se nenhum vizinho for informado,
   usa os bairros da mesma Região Urbana como aproximação, com aviso no laudo.
4. **Saneamento**: o R$/m² precisa ficar dentro do critério IQR `[Q1 − 1,5·IQR ; Q3 + 1,5·IQR]` **e** entre
   50% e 150% da mediana. A segunda faixa é necessária em amostras pequenas, em que o IQR sozinho não
   descarta leilões e erros de digitação.
5. `V_base = Mediana(R$/m²) × Área construída`.
6. **Fator terreno**: `(A_terreno / mediana dos terrenos da amostra)^0,25`, limitado a 0,85–1,15.
   Só entra quando a diferença passa de 20% e nunca para apartamentos.
7. **Melhorias** (teto de +25%): piscina 6%, gourmet 4%, armários 4%, energia solar 4%, alto padrão 5%,
   segurança 2%, edícula 3%*. Se o padrão construtivo é Alto, o acréscimo de "acabamento alto padrão" não é
   aplicado, porque as amostras comparáveis já são de alto padrão.
8. `Valor_Final = V_base × Fator_Terreno × (1 + Σ Melhorias)`, com faixa de ±10%.

\* A especificação original não define percentual para edícula. Foi adotado +3%; ajuste em `avm/models.py`.

As constantes técnicas ficam no topo de `avm/engine.py` e em `avm/models.py`.

## Infoimóveis

O Infoimóveis é o portal de referência em Campo Grande e já está ligado ao sistema
(`avm/scraper.py → fetch_infoimoveis`). O site é feito em Next.js, e o extrator lê os anúncios que vêm no HTML
público. Foi testado com uma página real do portal: os links montados batem com os links reais dos anúncios.

**Limitação atual:** a página de busca (`/busca`) não traz os resultados no HTML. Eles são carregados pelo
navegador a partir da API interna do portal, que tem proteção anti-robô e não é documentada. Este sistema
**não usa** essa API sem autorização. Por isso, hoje a fonte aparece como *"requer integração autorizada"*
na tela de resultado, em vez de devolver zero resultados em silêncio.

Para ativar a busca completa, peça ao Infoimóveis acesso à API ou a um feed de anúncios (XML/JSON) para uso
em avaliação. Com o acesso liberado, basta adaptar `fetch_infoimoveis`. O extrator e a montagem de links já
estão prontos.

## Bairros

A base (`data/bairros_campo_grande.json`) tem os bairros oficiais nas 7 Regiões Urbanas (PLANURB) e
os **nomes comerciais** que os portais usam para loteamentos (ex.: Água Limpa Park, com Região Urbana
sugerida). Como os portais têm centenas de nomes de loteamentos, **o formulário aceita qualquer bairro
digitado**. A pesquisa usa esse nome, e a comparação ignora acentos e prefixos como "Jardim", "Vila" e "Parque".
Para incluir um nome na lista, acrescente-o em `bairros_comerciais`.

## Coleta, cache e modo simulado

- **Cache SQLite** por fonte, bairro e tipo, com validade (TTL) de 7 dias (`CACHE_TTL_DAYS`). Evita bloqueios e acelera consultas repetidas. Resultados vazios não entram no cache.
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
  bairros.py                # bairros, nomes comerciais, vizinhança e regra "mesmo bairro"
  padrao.py                 # identificação do padrão construtivo pelo texto do anúncio
  extract.py                # extrator genérico (Next.js/RSC, JSON-LD, JSON embutido, cartões HTML)
  validators.py             # CPF, telefone, e-mail, CEP
  cep.py                    # ViaCEP + validação por faixa postal de Campo Grande
  scraper.py                # Infoimóveis, VivaReal, ZAP, OLX (+ ZenRows/ScraperAPI)
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
