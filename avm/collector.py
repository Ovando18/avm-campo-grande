"""Orquestra a coleta: cache (TTL) -> portais online -> mock (somente se tudo falhar)."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import mock
from .cache import SampleCache
from .config import Settings
from .models import Amostra
from .scraper import HttpClient, fetch_source

CIDADE = "*"


@dataclass
class ColetaStatus:
    modo: str = "online"  # online | cache | simulado
    fontes_ok: list[str] = field(default_factory=list)
    falhas: dict[str, str] = field(default_factory=dict)


class Coletor:
    def __init__(self, settings: Settings):
        self.s = settings
        self.cache = SampleCache(settings.cache_path, settings.cache_ttl_days)
        self.client = HttpClient(settings)
        self.status = ColetaStatus()
        self._mock = settings.force_mock
        self._fontes = [f.strip() for f in settings.scraper_sources.split(",") if f.strip()]

    def _coletar(self, tipo: str, bairro: str, area_ref: float, quartos_ref: int) -> list[Amostra]:
        if self._mock:
            return self._gerar_mock(tipo, bairro, area_ref, quartos_ref)
        amostras: list[Amostra] = []
        usou_cache = False
        for fonte in self._fontes:
            chave = SampleCache.chave(fonte, bairro, tipo)
            cached = self.cache.get(chave)
            if cached is not None:
                amostras += [Amostra.from_dict(d) for d in cached]
                usou_cache = True
                if fonte not in self.status.fontes_ok:
                    self.status.fontes_ok.append(fonte)
                continue
            try:
                res = fetch_source(self.client, fonte, tipo, None if bairro == CIDADE else bairro)
                self.cache.set(chave, [a.to_dict() for a in res])
                amostras += res
                if fonte not in self.status.fontes_ok:
                    self.status.fontes_ok.append(fonte)
            except Exception as exc:  # bloqueio, timeout, mudança de layout...
                self.status.falhas[fonte] = f"{type(exc).__name__}: {str(exc)[:120]}"
        if not self.status.fontes_ok:
            if not self.s.allow_mock:
                raise RuntimeError(
                    "Nenhuma fonte online respondeu e o modo simulado está desabilitado (AVM_ALLOW_MOCK=false). "
                    f"Falhas: {self.status.falhas}"
                )
            self._mock = True
            return self._gerar_mock(tipo, bairro, area_ref, quartos_ref)
        if usou_cache and self.status.modo == "online" and not self.status.falhas:
            self.status.modo = "cache"
        return amostras

    def _gerar_mock(self, tipo, bairro, area_ref, quartos_ref) -> list[Amostra]:
        self.status.modo = "simulado"
        if bairro == CIDADE:
            return mock.gerar_cidade(tipo, area_ref, quartos_ref)
        return mock.gerar_bairro(bairro, tipo, area_ref, quartos_ref)

    def bairro(self, tipo: str, bairro: str, area_ref: float, quartos_ref: int) -> list[Amostra]:
        return self._coletar(tipo, bairro, area_ref, quartos_ref)

    def cidade(self, tipo: str, area_ref: float, quartos_ref: int) -> list[Amostra]:
        return self._coletar(tipo, CIDADE, area_ref, quartos_ref)
