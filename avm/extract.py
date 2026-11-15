"""Extrator genérico de anúncios a partir de HTML de páginas de resultados de busca.

Tenta, nesta ordem:
  1. JSON-LD (schema.org: Offer / Product / SingleFamilyResidence / Apartment / ItemList);
  2. JSON embutido em <script> (__NEXT_DATA__, application/json, window.__X__ = {...}) — busca recursiva
     por objetos que tenham chave de preço e de área;
  3. Cartões HTML: blocos com link que contenham "R$" e "m²" no texto.
Feito para ser resiliente a mudanças de layout; os campos ausentes ficam zerados.
"""
from __future__ import annotations

import json
import re
from typing import Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup

PRICE_KEYS = ("preco", "precovenda", "valor", "valorvenda", "price", "saleprice", "valor_venda", "preco_venda")
AREA_KEYS = ("areaconstruida", "area_construida", "areautil", "area_util", "areaprivativa", "usablearea", "usableareas",
             "area", "areatotalconstruida", "floorsize", "metragem")
LAND_KEYS = ("areaterreno", "area_terreno", "terreno", "areatotal", "area_total", "totalarea", "totalareas", "lotsize")
ROOM_KEYS = ("quartos", "dormitorios", "bedrooms", "numberofbedrooms", "numberofrooms", "qtdquartos", "rooms")
BATH_KEYS = ("banheiros", "bathrooms", "numberofbathroomstotal", "qtdbanheiros")
PARK_KEYS = ("vagas", "garagem", "garagens", "parkingspaces", "vagasgaragem")
HOOD_KEYS = ("bairro", "neighborhood", "neighbourhood", "bairronome", "nomebairro")
URL_KEYS = ("url", "link", "href", "permalink", "urlanuncio")
TEXT_KEYS = ("titulo", "title", "name", "descricao", "description", "subject")


def br_num(v) -> float:
    if isinstance(v, bool):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, list):
        return br_num(v[0]) if v else 0.0
    if isinstance(v, dict):
        for k in ("value", "valor", "price", "minValue"):
            if k in v:
                return br_num(v[k])
        return 0.0
    s = re.sub(r"[^0-9,.]", "", str(v or ""))
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.search(r"\.\d{3}(\.|$)", s):
        s = s.replace(".", "")
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0


def _pick(d: dict, keys: tuple[str, ...]):
    low = {re.sub(r"[^a-z0-9_]", "", str(k).lower()): v for k, v in d.items()}
    for k in keys:
        if k in low and low[k] not in (None, "", [], {}):
            return low[k]
        k2 = k.replace("_", "")
        for lk, v in low.items():
            if lk.replace("_", "") == k2 and v not in (None, "", [], {}):
                return v
    return None


def _walk(o) -> Iterator[dict]:
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)


def _slug(txt: str) -> str:
    import unicodedata

    t = unicodedata.normalize("NFKD", str(txt)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def _from_obj(d: dict, base_url: str) -> dict | None:
    fin = d.get("finalidade")
    if isinstance(fin, dict):
        fin = fin.get("slug") or fin.get("nome")
    if fin and "venda" not in str(fin).lower():
        return None  # aluguel/temporada
    price = _pick(d, PRICE_KEYS)
    if price is None and isinstance(d.get("offers"), (dict, list)):
        off = d["offers"][0] if isinstance(d["offers"], list) and d["offers"] else d["offers"]
        price = off.get("price") if isinstance(off, dict) else None
    area = _pick(d, AREA_KEYS)
    p, a = br_num(price), br_num(area)
    if p < 20_000 or a < 15 or a > 20_000:  # descarta aluguel/condomínio/ruído
        return None
    hood = _pick(d, HOOD_KEYS)
    if hood is None and isinstance(d.get("address"), dict):
        hood = _pick(d["address"], HOOD_KEYS + ("addresslocality",))
    if isinstance(hood, dict):
        hood = _pick(hood, ("nome", "name", "descricao"))
    url = _pick(d, URL_KEYS)
    if isinstance(url, dict):
        url = _pick(url, ("href", "url"))
    if not url and d.get("id") and all(isinstance(d.get(k), str) for k in ("tipo", "bairro", "cidade", "estado")):
        # padrão de URL pública do Infoimóveis: /imovel/<finalidade>-<tipo>-<uf>-<cidade>-<bairro>/<id>
        url = "/imovel/" + "-".join(_slug(x) for x in (fin or "venda", d["tipo"], d["estado"], d["cidade"], d["bairro"])) + f"/{d['id']}"
    texto = " ".join(str(x) for x in (_pick(d, ("titulo", "title", "name", "subject")), _pick(d, ("descricao", "description"))) if x)
    return {
        "preco": p, "area_construida": a, "area_terreno": br_num(_pick(d, LAND_KEYS)),
        "quartos": int(br_num(_pick(d, ROOM_KEYS))), "banheiros": int(br_num(_pick(d, BATH_KEYS))),
        "vagas": int(br_num(_pick(d, PARK_KEYS))), "bairro": str(hood or ""),
        "url": urljoin(base_url, str(url)) if url else "", "titulo": texto[:600],
        "cidade": str(d.get("cidade") or ""),
    }


def _rsc_objects(html: str) -> Iterator[object]:
    """Next.js App Router: dados vêm em self.__next_f.push([1,"..."]); decodifica e extrai objetos JSON."""
    partes = re.findall(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', html)
    if not partes:
        return
    try:
        txt = "".join(json.loads(p) for p in partes)
    except ValueError:
        return
    dec = json.JSONDecoder()
    for m in re.finditer(r'[\[{]"?(?=[^\]]{0,40}"(?:valor|preco|price)")', txt):
        try:
            obj, _ = dec.raw_decode(txt, m.start())
            yield obj
        except ValueError:
            continue


def _json_blobs(soup: BeautifulSoup, html: str = "") -> Iterator[object]:
    yield from _rsc_objects(html)
    for tag in soup.find_all("script"):
        raw = (tag.string or tag.get_text() or "").strip()
        if not raw:
            continue
        typ = (tag.get("type") or "").lower()
        if "json" in typ or tag.get("id") == "__NEXT_DATA__":
            try:
                yield json.loads(raw)
            except ValueError:
                continue
        else:
            for m in re.finditer(r"=\s*(\{.*?\})\s*;?\s*(?:</|$|\n)", raw, re.S):
                try:
                    yield json.loads(m.group(1))
                except ValueError:
                    continue


_RE_PRECO = re.compile(r"R\$\s*([\d\.]{4,}(?:,\d{2})?)")
_RE_AREA = re.compile(r"(\d{2,5}(?:[\.,]\d{1,2})?)\s*m(?:²|2)\b", re.I)
_RE_Q = re.compile(r"(\d+)\s*(?:quartos?|dorms?\.?|dormit[óo]rios?|su[íi]tes?)", re.I)
_RE_B = re.compile(r"(\d+)\s*banheir", re.I)
_RE_V = re.compile(r"(\d+)\s*vagas?", re.I)


def _from_cards(soup: BeautifulSoup, base_url: str) -> list[dict]:
    out, vistos = [], set()
    for a in soup.find_all("a", href=True):
        bloco = a
        for _ in range(4):  # sobe até achar um contêiner com preço e área
            txt = bloco.get_text(" ", strip=True)
            if _RE_PRECO.search(txt) and _RE_AREA.search(txt):
                break
            bloco = bloco.parent or bloco
        txt = bloco.get_text(" ", strip=True)
        mp, areas = _RE_PRECO.search(txt), [br_num(x) for x in _RE_AREA.findall(txt)]
        if not mp or not areas or len(txt) > 1500:
            continue
        href = urljoin(base_url, a["href"])
        if href in vistos:
            continue
        vistos.add(href)
        q, b, v = _RE_Q.search(txt), _RE_B.search(txt), _RE_V.search(txt)
        out.append({
            "preco": br_num(mp.group(1)), "area_construida": min(areas),
            "area_terreno": max(areas) if len(areas) > 1 else 0.0,
            "quartos": int(q.group(1)) if q else 0, "banheiros": int(b.group(1)) if b else 0,
            "vagas": int(v.group(1)) if v else 0, "bairro": "", "url": href, "titulo": txt[:600], "cidade": "",
        })
    return [o for o in out if o["preco"] >= 20_000 and o["area_construida"] >= 15]


def extrair_anuncios(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    achados: list[dict] = []
    for blob in _json_blobs(soup, html):
        for obj in _walk(blob):
            item = _from_obj(obj, base_url)
            if item:
                achados.append(item)
    if not achados:
        achados = _from_cards(soup, base_url)
    # remove duplicados (mesmo objeto aparece em vários níveis do JSON)
    uniq, vistos = [], set()
    for it in achados:
        k = (it["url"] or "", round(it["preco"]), round(it["area_construida"]))
        if k not in vistos:
            vistos.add(k)
            uniq.append(it)
    return uniq
