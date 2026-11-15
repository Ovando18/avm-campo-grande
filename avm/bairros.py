"""Base oficial de bairros de Campo Grande/MS agrupados por Região Urbana."""
from __future__ import annotations

import json
import unicodedata
from functools import lru_cache

from .config import DATA_DIR

OUTRO = "Outro / Condomínio"


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return " ".join(text.lower().replace("-", " ").split())


@lru_cache(maxsize=1)
def load() -> dict:
    with open(DATA_DIR / "bairros_campo_grande.json", encoding="utf-8") as fh:
        return json.load(fh)


def regioes() -> list[str]:
    return list(load()["regioes"].keys())


def todos_bairros() -> list[str]:
    return sorted({b for lst in load()["regioes"].values() for b in lst}, key=normalize)


def opcoes_select() -> list[str]:
    """Bairros oficiais + loteamentos populares (aliases) + opção Outro."""
    aliases = [a for a in load()["aliases"] if not a.startswith("_")]
    return sorted(set(todos_bairros()) | set(aliases), key=normalize) + [OUTRO]


def resolver(nome: str) -> str | None:
    """Converte nome digitado/alias para o bairro oficial (ou None se desconhecido)."""
    n = normalize(nome)
    for b in todos_bairros():
        if normalize(b) == n:
            return b
    for alias, oficial in load()["aliases"].items():
        if normalize(alias) == n:
            return oficial
    return None


def regiao_de(bairro: str) -> str | None:
    oficial = resolver(bairro) or bairro
    for reg, lst in load()["regioes"].items():
        if oficial in lst:
            return reg
    return None


def bairros_da_regiao(regiao: str) -> list[str]:
    return list(load()["regioes"].get(regiao, []))


def regioes_adjacentes(regiao: str) -> list[str]:
    return list(load()["regioes_adjacentes"].get(regiao, []))


def niveis_fallback(bairro: str, regiao: str | None = None) -> list[tuple[str, list[str]]]:
    """Sequência de expansão geográfica: bairro -> região urbana -> regiões adjacentes -> município."""
    oficial = resolver(bairro) or bairro
    reg = regiao or regiao_de(oficial)
    niveis: list[tuple[str, list[str]]] = [(f"Bairro {oficial}", [oficial])]
    if reg:
        niveis.append((f"Região Urbana {reg}", bairros_da_regiao(reg)))
        adj = [b for r in regioes_adjacentes(reg) for b in bairros_da_regiao(r)]
        niveis.append((f"Regiões adjacentes a {reg}", bairros_da_regiao(reg) + adj))
    niveis.append(("Município de Campo Grande", todos_bairros()))
    return niveis


def preco_referencia(bairro: str) -> float:
    ref = load()["preco_m2_referencia"]
    oficial = resolver(bairro) or bairro
    if oficial in ref["bairro"]:
        return float(ref["bairro"][oficial])
    reg = regiao_de(oficial)
    return float(ref["regiao"].get(reg or "", 3800))
