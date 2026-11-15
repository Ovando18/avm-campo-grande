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


FATOR_PADRAO = {"Baixo": 0.78, "Normal": 1.0, "Alto": 1.32}


def gerar_bairro(bairro: str, tipo: str, area_ref: float, quartos_ref: int, n: int | None = None,
                 padrao: str = "Normal", regiao: str | None = None) -> list[Amostra]:
    rng = _rng(bairro, tipo, round(area_ref, -1), quartos_ref)
    n = n if n is not None else int(rng.integers(5, 16))
    base = bairros_mod.preco_referencia(bairro, regiao) * FATOR_TIPO.get(tipo, 1.0)
    out: list[Amostra] = []
    slug = bairros_mod.normalize(bairro).replace(" ", "-")
    for i in range(n):
        area = float(np.clip(rng.normal(area_ref, area_ref * 0.22), 35, 1200))
        # ~65% do mesmo padrão do avaliando, o restante de outros padrões (exercita o filtro de padrão)
        pad = padrao if rng.random() < 0.65 else str(rng.choice([p for p in FATOR_PADRAO if p != padrao]))
        unit = base * FATOR_PADRAO[pad] * float(rng.lognormal(0, 0.12))
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
                padrao=pad,
            )
        )
    if n >= 6:  # outliers controlados
        a = out[0]
        out.append(Amostra("Simulado", bairro, tipo, round(a.preco * 0.42, -3), a.area_construida, a.area_terreno, a.quartos, a.banheiros, a.vagas, a.url + "-leilao", True, padrao))
        b = out[1]
        out.append(Amostra("Simulado", bairro, tipo, round(b.preco * 2.6, -3), b.area_construida, b.area_terreno, b.quartos, b.banheiros, b.vagas, b.url + "-erro", True, padrao))
    return out


def gerar_cidade(tipo: str, area_ref: float, quartos_ref: int, padrao: str = "Normal") -> list[Amostra]:
    out: list[Amostra] = []
    for b in bairros_mod.todos_bairros():
        out.extend(gerar_bairro(b, tipo, area_ref, quartos_ref, n=int(_rng("cidade", b, tipo).integers(1, 4)), padrao=padrao))
    return out
