"""Gerador inteligente de amostras SIMULADAS (modo demonstração).

Ativado automaticamente apenas quando todas as fontes online falham (bloqueio/offline) e
AVM_ALLOW_MOCK=true. Gera amostras determinísticas e plausíveis por bairro, incluindo
alguns outliers (leilão / erro de digitação) para exercitar o saneamento estatístico.
"""
from __future__ import annotations

import hashlib

import numpy as np

from . import bairros as bairros_mod
from .models import Amostra

FATOR_TIPO = {"Casa Térrea": 0.95, "Sobrado": 1.0, "Casa em Condomínio Fechado": 1.22, "Apartamento": 1.08}


def _rng(*parts) -> np.random.Generator:
    seed = int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12], 16)
    return np.random.default_rng(seed)


def gerar_bairro(bairro: str, tipo: str, area_ref: float, quartos_ref: int, n: int | None = None) -> list[Amostra]:
    rng = _rng(bairro, tipo, round(area_ref, -1), quartos_ref)
    n = n if n is not None else int(rng.integers(3, 13))
    base = bairros_mod.preco_referencia(bairro) * FATOR_TIPO.get(tipo, 1.0)
    out: list[Amostra] = []
    slug = bairros_mod.normalize(bairro).replace(" ", "-")
    for i in range(n):
        area = float(np.clip(rng.normal(area_ref, area_ref * 0.22), 35, 1200))
        unit = base * float(rng.lognormal(0, 0.12))
        terreno = 0.0 if tipo == "Apartamento" else float(round(max(area * rng.uniform(1.4, 3.2), 140), 0))
        quartos = int(np.clip(quartos_ref + rng.integers(-1, 2), 1, 6))
        out.append(
            Amostra(
                fonte="Simulado",
                bairro=bairro,
                tipo=tipo,
                preco=float(round(unit * area, -3)),
                area_construida=round(area, 1),
                area_terreno=terreno,
                quartos=quartos,
                banheiros=int(np.clip(quartos - rng.integers(0, 2), 1, 6)),
                vagas=int(rng.integers(1, 4)),
                url=f"https://exemplo.invalid/simulacao/{slug}/{i + 1}",
                simulada=True,
            )
        )
    if n >= 6:  # outliers controlados
        a = out[0]
        out.append(Amostra("Simulado", bairro, tipo, round(a.preco * 0.42, -3), a.area_construida, a.area_terreno, a.quartos, a.banheiros, a.vagas, a.url + "-leilao", True))
        b = out[1]
        out.append(Amostra("Simulado", bairro, tipo, round(b.preco * 2.6, -3), b.area_construida, b.area_terreno, b.quartos, b.banheiros, b.vagas, b.url + "-erro", True))
    return out


def gerar_cidade(tipo: str, area_ref: float, quartos_ref: int) -> list[Amostra]:
    out: list[Amostra] = []
    for b in bairros_mod.todos_bairros():
        out.extend(gerar_bairro(b, tipo, area_ref, quartos_ref, n=int(_rng("cidade", b, tipo).integers(1, 4))))
    return out
