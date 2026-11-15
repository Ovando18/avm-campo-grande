"""Configuração centralizada: lê de variáveis de ambiente (.env) e, se disponível, de st.secrets."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

try:  # carrega .env em desenvolvimento local
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:  # pragma: no cover
    pass


def _get(key: str, default: str = "") -> str:
    val = os.getenv(key)
    if val is None:
        try:
            import streamlit as st

            if key in st.secrets:
                val = str(st.secrets[key])
        except Exception:
            val = None
    return default if val is None else val


def _bool(key: str, default: bool) -> bool:
    return _get(key, str(default)).strip().lower() in {"1", "true", "yes", "sim", "on"}


@dataclass(frozen=True)
class Settings:
    company_name: str = field(default_factory=lambda: _get("COMPANY_NAME", "Sua Empresa de Avaliações Ltda."))
    company_cnpj: str = field(default_factory=lambda: _get("COMPANY_CNPJ", "00.000.000/0001-00"))
    company_address: str = field(
        default_factory=lambda: _get("COMPANY_ADDRESS", "Av. Afonso Pena, 0000 — Centro, Campo Grande/MS")
    )
    company_phone: str = field(default_factory=lambda: _get("COMPANY_PHONE", "(67) 3000-0000"))
    company_email: str = field(default_factory=lambda: _get("COMPANY_EMAIL", "contato@suaempresa.com.br"))
    company_logo: str = field(default_factory=lambda: _get("COMPANY_LOGO_PATH", str(ROOT / "assets" / "logo.png")))
    responsavel_tecnico: str = field(default_factory=lambda: _get("RESPONSAVEL_TECNICO", ""))

    scraper_provider: str = field(default_factory=lambda: _get("SCRAPER_PROVIDER", "none").lower())
    zenrows_api_key: str = field(default_factory=lambda: _get("ZENROWS_API_KEY"))
    scraperapi_key: str = field(default_factory=lambda: _get("SCRAPERAPI_KEY"))
    scraper_timeout: int = field(default_factory=lambda: int(_get("SCRAPER_TIMEOUT", "20")))
    scraper_sources: str = field(default_factory=lambda: _get("SCRAPER_SOURCES", "infoimoveis,vivareal,zap,olx"))
    infoimoveis_search_url: str = field(
        default_factory=lambda: _get(
            "INFOIMOVEIS_SEARCH_URL",
            "https://www.infoimoveis.com.br/busca?finalidade=venda&tipos={tipo}&estado=ms&cidade=campo-grande&bairros={bairro}&pagina={pagina}",
        )
    )

    allow_mock: bool = field(default_factory=lambda: _bool("AVM_ALLOW_MOCK", True))
    force_mock: bool = field(default_factory=lambda: _bool("AVM_FORCE_MOCK", False))
    cache_path: str = field(default_factory=lambda: _get("CACHE_DB_PATH", str(DATA_DIR / "cache.sqlite3")))
    cache_ttl_days: int = field(default_factory=lambda: int(_get("CACHE_TTL_DAYS", "7")))


def get_settings() -> Settings:
    return Settings()
