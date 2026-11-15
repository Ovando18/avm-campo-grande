"""Coleta online de ofertas de venda em portais imobiliários de Campo Grande/MS.

Fontes (best-effort; portais mudam layout/endpoints e aplicam anti-bot com frequência):
  * Infoimóveis (infoimoveis.com.br) — portal de referência em MS. Lê anúncios presentes no HTML público
    (payload Next.js/RSC, JSON-LD ou cartões). Busca completa depende de integração autorizada com o portal.
  * VivaReal e ZAP Imóveis — API pública de busca (glue-api) usada pelos próprios sites.
  * OLX — página de resultados (JSON embutido em __NEXT_DATA__).

Em produção, configure SCRAPER_PROVIDER=zenrows|scraperapi para rotacionar IPs e evitar bloqueios.
Qualquer falha de rede/bloqueio é registrada em `status` e o coletor decide pelo fallback (cache ou mock).
"""
from __future__ import annotations

import json
import re
from urllib.parse import quote, urlencode

import requests
from bs4 import BeautifulSoup

from . import bairros as bairros_mod
from .config import Settings
from .extract import extrair_anuncios
from .models import Amostra
from .padrao import inferir_padrao

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36"
)

GLUE_UNIT_TYPES = {
    "Casa Térrea": ("HOME", "UnitSubType_NONE,SINGLE_STOREY_HOUSE,VILLAGE_HOUSE,KITNET", "RESIDENTIAL"),
    "Sobrado": ("TWO_STORY_HOUSE", "", "RESIDENTIAL"),
    "Casa em Condomínio Fechado": ("CONDOMINIUM", "", "RESIDENTIAL"),
    "Apartamento": ("APARTMENT", "", "RESIDENTIAL"),
}
OLX_PATH = {
    "Casa Térrea": "casas",
    "Sobrado": "casas",
    "Casa em Condomínio Fechado": "casas",
    "Apartamento": "apartamentos",
}


class ScraperBlocked(Exception):
    pass


class HttpClient:
    def __init__(self, settings: Settings):
        self.s = settings
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"})

    def get(self, url: str, headers: dict | None = None) -> requests.Response:
        headers = headers or {}
        prov = self.s.scraper_provider
        if prov == "zenrows" and self.s.zenrows_api_key:
            params = {"apikey": self.s.zenrows_api_key, "url": url, "premium_proxy": "true", "proxy_country": "br"}
            if headers:
                params["custom_headers"] = "true"
            r = self.session.get("https://api.zenrows.com/v1/", params=params, headers=headers, timeout=self.s.scraper_timeout + 40)
        elif prov == "scraperapi" and self.s.scraperapi_key:
            params = {"api_key": self.s.scraperapi_key, "url": url, "country_code": "br"}
            if headers:
                params["keep_headers"] = "true"
            r = self.session.get("https://api.scraperapi.com/", params=params, headers=headers, timeout=self.s.scraper_timeout + 40)
        else:
            r = self.session.get(url, headers=headers, timeout=self.s.scraper_timeout)
        if r.status_code in (401, 403, 429, 503):
            raise ScraperBlocked(f"HTTP {r.status_code}")
        r.raise_for_status()
        return r


def _num(v) -> float:
    """Converte números em formato brasileiro ("R$ 1.250.000", "120m²", "1.250,50") ou listas da API."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, list):
        return _num(v[0]) if v else 0.0
    s = re.sub(r"[^0-9,.]", "", str(v or ""))
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.search(r"\.\d{3}(\.|$)", s):
        s = s.replace(".", "")
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0


def _resolve_bairro(nome: str, default: str) -> str:
    """Mantém o nome do bairro como anunciado (loteamentos como "Água Limpa Park" não são fundidos ao oficial)."""
    return bairros_mod.nome_canonico(nome) if nome else default


# ----------------------------------------------------------------------------- VivaReal / ZAP
def fetch_glue(client: HttpClient, portal: str, tipo: str, bairro: str | None, max_items: int = 200) -> list[Amostra]:
    host, domain, fonte = {
        "vivareal": ("glue-api.vivareal.com", "www.vivareal.com.br", "VivaReal"),
        "zap": ("glue-api.zapimoveis.com.br", "www.zapimoveis.com.br", "ZAP Imóveis"),
    }[portal]
    unit, subtypes, usage = GLUE_UNIT_TYPES[tipo]
    out: list[Amostra] = []
    for start in range(0, max_items, 100):
        params = {
            "addressCity": "Campo Grande",
            "addressState": "Mato Grosso do Sul",
            "addressLocationId": "BR>Mato Grosso do Sul>NULL>Campo Grande" + (f">Barrios>{bairro}" if bairro else ""),
            "addressNeighborhood": bairro or "",
            "business": "SALE",
            "listingType": "USED",
            "unitTypes": unit,
            "unitSubTypes": subtypes,
            "usageTypes": usage,
            "categoryPage": "RESULT",
            "size": 100,
            "from": start,
            "includeFields": "search(result(listings(listing(title,description,usableAreas,totalAreas,bedrooms,bathrooms,parkingSpaces,pricingInfos,address,unitTypes),link)),totalCount)",
        }
        url = f"https://{host}/v2/listings?{urlencode(params)}"
        r = client.get(url, headers={"x-domain": domain, "Origin": f"https://{domain}", "Referer": f"https://{domain}/"})
        data = r.json()
        listings = data.get("search", {}).get("result", {}).get("listings", [])
        for item in listings:
            lst = item.get("listing", {})
            price = next(
                (_num(p.get("price")) for p in lst.get("pricingInfos", []) if p.get("businessType") == "SALE"), 0.0
            )
            area = _num(lst.get("usableAreas"))
            if price <= 0 or area <= 0:
                continue
            href = item.get("link", {}).get("href", "")
            texto = f"{lst.get('title', '')} {lst.get('description', '')}"
            out.append(
                Amostra(
                    fonte=fonte,
                    bairro=_resolve_bairro(lst.get("address", {}).get("neighborhood", ""), bairro or ""),
                    tipo=tipo,
                    preco=price,
                    area_construida=area,
                    area_terreno=_num(lst.get("totalAreas")) if tipo != "Apartamento" else 0.0,
                    quartos=int(_num(lst.get("bedrooms"))),
                    banheiros=int(_num(lst.get("bathrooms"))),
                    vagas=int(_num(lst.get("parkingSpaces"))),
                    url=f"https://{domain}{href}" if href.startswith("/") else href,
                    padrao=inferir_padrao(texto),
                    titulo=texto[:300],
                )
            )
        total = data.get("search", {}).get("totalCount", 0)
        if start + 100 >= min(total, max_items) or not listings:
            break
    return out


# ----------------------------------------------------------------------------- OLX
def fetch_olx(client: HttpClient, tipo: str, bairro: str | None, pages: int = 2) -> list[Amostra]:
    out: list[Amostra] = []
    base = f"https://www.olx.com.br/imoveis/venda/{OLX_PATH[tipo]}/estado-ms/regiao-de-campo-grande/campo-grande"
    for page in range(1, pages + 1):
        q = {"o": page}
        if bairro:
            q["q"] = bairro
        r = client.get(f"{base}?{urlencode(q, quote_via=quote)}")
        soup = BeautifulSoup(r.text, "html.parser")
        tag = soup.find("script", id="__NEXT_DATA__")
        if not tag:
            raise ScraperBlocked("OLX: estrutura de página não reconhecida")
        ads = json.loads(tag.string or "{}").get("props", {}).get("pageProps", {}).get("ads", [])
        for ad in ads:
            props = {p.get("name"): p.get("value") for p in ad.get("properties", []) if isinstance(p, dict)}
            price = _num(ad.get("price") or ad.get("priceValue"))
            area = _num(props.get("size"))
            if price <= 0 or area <= 0:
                continue
            if tipo == "Sobrado" and "sobrado" not in (ad.get("subject", "") + props.get("category", "")).lower():
                continue
            if tipo == "Casa em Condomínio Fechado" and "condom" not in ad.get("subject", "").lower():
                continue
            loc = ad.get("locationDetails", {}) or {}
            out.append(
                Amostra(
                    fonte="OLX",
                    bairro=_resolve_bairro(loc.get("neighbourhood", ""), bairro or ""),
                    tipo=tipo,
                    preco=price,
                    area_construida=area,
                    area_terreno=0.0,
                    quartos=int(_num(props.get("rooms"))),
                    banheiros=int(_num(props.get("bathrooms"))),
                    vagas=int(_num(props.get("garage_spaces"))),
                    url=ad.get("url", ""),
                    padrao=inferir_padrao(ad.get("subject", "")),
                    titulo=ad.get("subject", "")[:300],
                )
            )
        if not ads:
            break
    return out


# ----------------------------------------------------------------------------- Infoimóveis
# Slugs de tipo usados pelo Infoimóveis (observados nas URLs públicas /imovel/venda-<tipo>-ms-campo-grande-<bairro>/<id>)
INFO_TIPO = {
    "Casa Térrea": "casa-terrea",
    "Sobrado": "sobrado",
    "Casa em Condomínio Fechado": "casa-terrea-condominio",
    "Apartamento": "apartamento",
}


class FonteIndisponivel(Exception):
    pass


def _slug(txt: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", bairros_mod.normalize(txt)).strip("-")


def fetch_infoimoveis(client: HttpClient, tipo: str, bairro: str | None, pages: int = 3) -> list[Amostra]:
    """Busca de venda no Infoimóveis (portal de referência em MS).

    O site é Next.js: quando a página pública traz os anúncios no HTML (payload RSC), eles são lidos aqui.
    Atualmente a página /busca carrega os resultados no navegador a partir da API interna do portal, que
    exige integração autorizada (não é usada por este sistema). Nesse caso a fonte é reportada como
    indisponível — nunca como "zero resultados". URL configurável via INFOIMOVEIS_SEARCH_URL.
    """
    tpl = client.s.infoimoveis_search_url
    out: list[Amostra] = []
    for page in range(1, pages + 1):
        url = tpl.format(tipo=INFO_TIPO[tipo], bairro=_slug(bairro) if bairro else "", pagina=page)
        if not bairro:
            url = re.sub(r"&bairros=(?=&|$)", "", url)
        r = client.get(url, headers={"Referer": "https://www.infoimoveis.com.br/"})
        if "Just a moment" in r.text[:2000]:
            raise ScraperBlocked("Infoimóveis: proteção anti-robô ativa")
        itens = [it for it in extrair_anuncios(r.text, "https://www.infoimoveis.com.br/")
                 if not it["cidade"] or bairros_mod.normalize(it["cidade"]) == "campo grande"]
        if not itens:
            if page == 1:
                raise FonteIndisponivel(
                    "Infoimóveis carrega os resultados da busca pela API interna do portal; "
                    "é necessária integração autorizada (veja o README)."
                )
            break
        for it in itens:
            nome_bairro = it["bairro"] or bairro or ""
            out.append(
                Amostra(
                    fonte="Infoimóveis", bairro=_resolve_bairro(nome_bairro, bairro or ""), tipo=tipo,
                    preco=it["preco"], area_construida=it["area_construida"],
                    area_terreno=it["area_terreno"] if tipo != "Apartamento" else 0.0,
                    quartos=it["quartos"], banheiros=it["banheiros"], vagas=it["vagas"],
                    url=it["url"] or "",
                    padrao=inferir_padrao(it["titulo"]), titulo=it["titulo"][:300],
                )
            )
    return out


def fetch_source(client: HttpClient, fonte: str, tipo: str, bairro: str | None) -> list[Amostra]:
    if fonte == "infoimoveis":
        return fetch_infoimoveis(client, tipo, bairro)
    if fonte in ("vivareal", "zap"):
        return fetch_glue(client, fonte, tipo, bairro)
    if fonte == "olx":
        return fetch_olx(client, tipo, bairro)
    raise ValueError(f"Fonte desconhecida: {fonte}")
