"""Identificação do padrão construtivo de um anúncio a partir do título/descrição (palavras-chave)."""
from __future__ import annotations

import re

from .bairros import normalize

_ALTO = [
    r"alto padrao", r"altissimo padrao", r"luxo", r"luxuos", r"porcelanato", r"gesso", r"sanca", r"planejad",
    r"piscina", r"gourmet", r"suite master", r"pe direito duplo", r"automacao", r"projeto arquitet",
    r"marmore", r"granito", r"espaco gourmet", r"closet", r"home theater", r"\b4 suites\b", r"\b3 suites\b",
]
_BAIXO = [
    r"popular", r"simples", r"precisa de reforma", r"para reforma", r"reformar", r"necessita reforma",
    r"minha casa minha vida", r"\bmcmv\b", r"casa verde e amarela", r"financiamento caixa facil", r"sem acabamento",
    r"inacabad", r"forro de pvc", r"\bcohab\b", r"conjunto habitacional", r"barracao",
]


def inferir_padrao(texto: str) -> str:
    """Retorna "Alto", "Baixo", "Normal" ou "" (sem informação suficiente)."""
    t = normalize(texto)
    if len(t) < 15:
        return ""
    alto = sum(bool(re.search(p, t)) for p in _ALTO)
    baixo = sum(bool(re.search(p, t)) for p in _BAIXO)
    if baixo >= 1 and alto <= 1:
        return "Baixo"
    if alto >= 2 or re.search(r"alto padrao|luxo", t):
        return "Alto"
    return "Normal"


def compativel(padrao_avaliando: str, padrao_amostra: str) -> bool:
    """Mesmo padrão. Amostras sem padrão identificado são mantidas (o saneamento IQR trata desvios)."""
    return not padrao_amostra or padrao_amostra == padrao_avaliando
