"""Base de bairros de Campo Grande/MS: 74 bairros oficiais (7 Regiões Urbanas) + nomes comerciais usados
pelos portais (loteamentos como "Água Limpa Park"). Qualquer outro nome digitado também é aceito."""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache

from .config import DATA_DIR

OUTRO = "Outro / Condomínio"
_PREFIXOS = r"^(jardim|jd|vila|vl|parque|pq|residencial|res|conjunto|conj|loteamento|bairro|condominio|cond)\.? +"


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return " ".join(text.lower().replace("-", " ").split())


def chave(nome: str) -> str:
    """Chave de comparação tolerante: sem acento/caixa e sem prefixos genéricos (Jardim, Vila, Parque...)."""
    n = normalize(nome)
    n2 = re.sub(_PREFIXOS, "", n)
    return n2 or n


@lru_cache(maxsize=1)
def load() -> dict:
    with open(DATA_DIR / "bairros_campo_grande.json", encoding="utf-8") as fh:
        return json.load(fh)


def regioes() -> list[str]:
    return list(load()["regioes"].keys())


def todos_bairros() -> list[str]:
    return sorted({b for lst in load()["regioes"].values() for b in lst}, key=normalize)


def comerciais() -> dict[str, str]:
    return {k: v for k, v in load().get("bairros_comerciais", {}).items() if not k.startswith("_")}


def opcoes_select() -> list[str]:
    """Bairros oficiais + nomes comerciais/loteamentos + aliases (lista para busca no formulário)."""
    aliases = [a for a in load()["aliases"] if not a.startswith("_")]
    return sorted(set(todos_bairros()) | set(aliases) | set(comerciais()), key=normalize)


def oficial(nome: str) -> str | None:
    """Bairro oficial correspondente (ou None se for um loteamento/nome não mapeado)."""
    c = chave(nome)
    for b in todos_bairros():
        if chave(b) == c:
            return b
    for alias, of in load()["aliases"].items():
        if chave(alias) == c:
            return of
    return None


def nome_canonico(nome: str) -> str:
    """Nome usado na pesquisa: o próprio nome digitado (com grafia da base, se existir)."""
    c = chave(nome)
    for b in todos_bairros() + opcoes_select():  # grafia oficial tem prioridade
        if chave(b) == c:
            return b
    return " ".join((nome or "").split())


def interpretar(digitado: str) -> str:
    """Interpreta o bairro digitado no formulário: grafia exata da base, ou a única opção da base que
    contém o texto digitado (ex.: "agua limpa" -> "Água Limpa Park"). Senão, mantém o texto digitado."""
    c = chave(digitado)
    if not c:
        return ""
    exato = nome_canonico(digitado)
    if chave(exato) == c and exato in opcoes_select():
        return exato
    candidatos = [b for b in opcoes_select() if c in chave(b) or c in normalize(b)]
    if len({oficial(b) or b for b in candidatos}) == 1:
        return min(candidatos, key=len)
    return " ".join(digitado.split()).title() if digitado.islower() else " ".join(digitado.split())


# compatibilidade com versões anteriores
def resolver(nome: str) -> str | None:
    return oficial(nome)


def regiao_de(bairro: str) -> str | None:
    of = oficial(bairro)
    if of:
        for reg, lst in load()["regioes"].items():
            if of in lst:
                return reg
    c = chave(bairro)
    for nome, reg in comerciais().items():
        if chave(nome) == c:
            return reg
    return None


def bairros_da_regiao(regiao: str) -> list[str]:
    return list(load()["regioes"].get(regiao, []))


def mesmo_bairro(a: str, b: str) -> bool:
    """Mesmo bairro: mesma grafia normalizada, ou ambos pertencem ao mesmo bairro oficial."""
    if chave(a) == chave(b):
        return True
    oa, ob = oficial(a), oficial(b)
    return bool(oa and ob and oa == ob)


def niveis_pesquisa(bairro: str, vizinhos: list[str], regiao: str | None) -> list[tuple[str, list[str], str]]:
    """Regra: 1º mesmo bairro; 2º (só se insuficiente) bairros vizinhos informados.
    Se nenhum vizinho foi informado, usa os bairros da mesma Região Urbana como aproximação (com aviso)."""
    niveis = [(f"Bairro {bairro}", [bairro], "bairro")]
    viz = [v for v in vizinhos if chave(v) != chave(bairro)]
    if viz:
        niveis.append(("Bairros vizinhos: " + ", ".join(viz), [bairro] + viz, "vizinhos"))
    else:
        reg = regiao or regiao_de(bairro)
        if reg:
            niveis.append((f"Bairros da Região Urbana {reg} (vizinhos não informados)", [bairro] + bairros_da_regiao(reg), "regiao"))
    return niveis


def preco_referencia(bairro: str, regiao: str | None = None) -> float:
    ref = load()["preco_m2_referencia"]
    of = oficial(bairro) or bairro
    if of in ref["bairro"]:
        return float(ref["bairro"][of])
    reg = regiao or regiao_de(bairro)
    return float(ref["regiao"].get(reg or "", 3800))
