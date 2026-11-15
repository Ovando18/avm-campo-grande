"""Motor de avaliação — regra da mediana homogeneizada (inspirado na NBR 14653-2).

Etapas:
 1. Coleta de ofertas (bairro -> fallback geográfico por região urbana / regiões adjacentes / município).
 2. Filtro de similaridade: área construída ±30% e quartos ±1 em relação ao avaliando.
 3. Saneamento de outliers no R$/m² pelo critério IQR (Q1 - 1,5·IQR ; Q3 + 1,5·IQR).
 4. V_base = Mediana(R$/m²) × Área construída do avaliando.
 5. Fator Terreno = (A_terreno_avaliando / Mediana A_terreno_amostras)^0,25, limitado a [0,85 ; 1,15],
    aplicado apenas quando a diferença supera 20% (não se aplica a apartamentos).
 6. Fator Melhorias = 1 + Σ percentuais (teto de +25%).
 7. Valor_Final = V_base × Fator_Terreno × (1 + Σ Melhorias); faixa de confiança ±10%.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import bairros as bairros_mod
from .collector import ColetaStatus, Coletor
from .models import MELHORIAS, TETO_MELHORIAS, Amostra, Imovel

MIN_AMOSTRAS = 5
MIN_ABSOLUTO = 3
TOL_AREA = 0.30
TOL_QUARTOS = 1
TERRENO_LIMIAR = 0.20
TERRENO_EXPOENTE = 0.25
TERRENO_LIMITES = (0.85, 1.15)
FAIXA = 0.10
TZ = ZoneInfo("America/Campo_Grande")


class AmostrasInsuficientes(Exception):
    pass


@dataclass
class Resultado:
    protocolo: str
    hash_integridade: str
    emitido_em: datetime
    valor_final: float
    valor_minimo: float
    valor_maximo: float
    valor_base: float
    mediana_unit: float
    media_unit: float
    cv_unit: float
    fator_terreno: float
    mediana_terreno_amostras: float
    soma_melhorias: float
    melhorias_aplicadas: list[tuple[str, float]]
    m2_construido: float
    m2_terreno: float
    nivel_geografico: str
    n_pesquisadas: int
    n_similares: int
    n_saneadas: int
    limites_iqr: tuple[float, float]
    amostras: pd.DataFrame
    outliers: pd.DataFrame
    status: ColetaStatus
    avisos: list[str] = field(default_factory=list)

    @property
    def simulado(self) -> bool:
        return self.status.modo == "simulado"


def _norm_quartos(q: int) -> int:
    return min(int(q), 5)


def filtrar_similares(amostras: list[Amostra], imovel: Imovel) -> list[Amostra]:
    a_min, a_max = imovel.area_construida * (1 - TOL_AREA), imovel.area_construida * (1 + TOL_AREA)
    q = _norm_quartos(imovel.quartos)
    out = []
    for a in amostras:
        if not (a_min <= a.area_construida <= a_max):
            continue
        if a.quartos and abs(_norm_quartos(a.quartos) - q) > TOL_QUARTOS:
            continue
        if q >= 5 and a.quartos and a.quartos < 4:
            continue
        out.append(a)
    return out


def deduplicar(amostras: list[Amostra]) -> list[Amostra]:
    """Remove o mesmo anúncio publicado em mais de um portal (preço + área + bairro)."""
    vistos, out = set(), []
    for a in amostras:
        k = (bairros_mod.normalize(a.bairro), round(a.preco, -3), round(a.area_construida))
        if k not in vistos:
            vistos.add(k)
            out.append(a)
    return out


def sanear_iqr(amostras: list[Amostra]) -> tuple[list[Amostra], list[Amostra], tuple[float, float]]:
    if len(amostras) < 4:
        return amostras, [], (float("-inf"), float("inf"))
    unit = np.array([a.preco_m2 for a in amostras])
    q1, q3 = np.percentile(unit, [25, 75])
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    keep = [a for a in amostras if lo <= a.preco_m2 <= hi]
    drop = [a for a in amostras if not (lo <= a.preco_m2 <= hi)]
    return keep, drop, (float(lo), float(hi))


def fator_terreno(imovel: Imovel, amostras: list[Amostra]) -> tuple[float, float]:
    terrenos = [a.area_terreno for a in amostras if a.area_terreno and a.area_terreno > 0]
    if imovel.tipo == "Apartamento" or imovel.area_terreno <= 0 or len(terrenos) < MIN_ABSOLUTO:
        return 1.0, float(np.median(terrenos)) if terrenos else 0.0
    med = float(np.median(terrenos))
    r = imovel.area_terreno / med
    if abs(r - 1) <= TERRENO_LIMIAR:
        return 1.0, med
    return float(np.clip(r**TERRENO_EXPOENTE, *TERRENO_LIMITES)), med


def fator_melhorias(chaves: list[str]) -> tuple[float, list[tuple[str, float]]]:
    aplicadas = [(MELHORIAS[k][0], MELHORIAS[k][1]) for k in chaves if k in MELHORIAS]
    return min(sum(p for _, p in aplicadas), TETO_MELHORIAS), aplicadas


def gerar_protocolo(imovel: Imovel, solicitante_cpf: str, quando: datetime) -> tuple[str, str]:
    raw = f"{imovel.to_dict()}|{solicitante_cpf}|{quando.isoformat()}"
    h = hashlib.sha256(raw.encode()).hexdigest()
    return f"AVM-CG-{quando.year}-{h[:6].upper()}", h


def _df(amostras: list[Amostra]) -> pd.DataFrame:
    cols = ["fonte", "bairro", "tipo", "area_construida", "area_terreno", "quartos", "banheiros", "vagas", "preco", "preco_m2", "url", "simulada"]
    if not amostras:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame([a.to_dict() for a in amostras])[cols].sort_values("preco_m2").reset_index(drop=True)


def avaliar(imovel: Imovel, coletor: Coletor, solicitante_cpf: str = "") -> Resultado:
    bairro = bairros_mod.resolver(imovel.bairro) or imovel.bairro
    niveis = bairros_mod.niveis_fallback(bairro, imovel.regiao)
    avisos: list[str] = []

    pool_bairro = coletor.bairro(imovel.tipo, bairro, imovel.area_construida, imovel.quartos)
    pool_cidade: list[Amostra] | None = None

    escolha = None
    for i, (rotulo, lista) in enumerate(niveis):
        if i == 0:
            candidatas = [a for a in pool_bairro if bairros_mod.normalize(a.bairro) == bairros_mod.normalize(bairro)] or pool_bairro
        else:
            if pool_cidade is None:
                pool_cidade = coletor.cidade(imovel.tipo, imovel.area_construida, imovel.quartos)
            alvo = {bairros_mod.normalize(b) for b in lista}
            candidatas = [a for a in pool_bairro + pool_cidade if bairros_mod.normalize(a.bairro) in alvo]
        candidatas = deduplicar(candidatas)
        similares = filtrar_similares(candidatas, imovel)
        saneadas, outliers, limites = sanear_iqr(similares)
        escolha = (rotulo, candidatas, similares, saneadas, outliers, limites)
        if len(saneadas) >= MIN_AMOSTRAS:
            break
        avisos.append(f"{rotulo}: {len(saneadas)} amostra(s) válida(s) — expandindo a pesquisa.")

    rotulo, candidatas, similares, saneadas, outliers, limites = escolha
    if len(saneadas) < MIN_ABSOLUTO:
        raise AmostrasInsuficientes(
            f"Foram encontradas apenas {len(saneadas)} amostras semelhantes em todo o município. "
            "Revise as características informadas (área/quartos) ou tente novamente mais tarde."
        )
    if len(saneadas) < MIN_AMOSTRAS:
        avisos.append(f"Amostra reduzida ({len(saneadas)} elementos): resultado com menor confiabilidade.")

    unit = np.array([a.preco_m2 for a in saneadas])
    mediana_unit = float(np.median(unit))
    media_unit = float(np.mean(unit))
    cv = float(np.std(unit, ddof=1) / media_unit) if len(unit) > 1 else 0.0

    v_base = mediana_unit * imovel.area_construida
    f_terr, med_terr = fator_terreno(imovel, saneadas)
    soma_mel, aplicadas = fator_melhorias(imovel.melhorias)
    valor = v_base * f_terr * (1 + soma_mel)
    if sum(p for _, p in aplicadas) > TETO_MELHORIAS:
        avisos.append("Soma das melhorias limitada ao teto técnico de +25%.")

    quando = datetime.now(TZ)
    protocolo, h = gerar_protocolo(imovel, solicitante_cpf, quando)
    return Resultado(
        protocolo=protocolo,
        hash_integridade=h,
        emitido_em=quando,
        valor_final=round(valor, 2),
        valor_minimo=round(valor * (1 - FAIXA), 2),
        valor_maximo=round(valor * (1 + FAIXA), 2),
        valor_base=round(v_base, 2),
        mediana_unit=mediana_unit,
        media_unit=media_unit,
        cv_unit=cv,
        fator_terreno=f_terr,
        mediana_terreno_amostras=med_terr,
        soma_melhorias=soma_mel,
        melhorias_aplicadas=aplicadas,
        m2_construido=valor / imovel.area_construida,
        m2_terreno=(valor / imovel.area_terreno) if imovel.area_terreno > 0 else 0.0,
        nivel_geografico=rotulo,
        n_pesquisadas=len(candidatas),
        n_similares=len(similares),
        n_saneadas=len(saneadas),
        limites_iqr=limites,
        amostras=_df(saneadas),
        outliers=_df(outliers),
        status=coletor.status,
        avisos=avisos,
    )
