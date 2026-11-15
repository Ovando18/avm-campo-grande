"""Estruturas de dados do domínio."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

TIPOS = ["Casa Térrea", "Sobrado", "Casa em Condomínio Fechado", "Apartamento"]

# Percentuais técnicos de valorização (ponderação incremental) — teto total de +25%.
MELHORIAS: dict[str, tuple[str, float]] = {
    "armarios": ("Armários planejados/embutidos", 0.04),
    "gourmet": ("Área gourmet / Churrasqueira", 0.04),
    "piscina": ("Piscina", 0.06),
    "solar": ("Energia solar (fotovoltaica)", 0.04),
    "alto_padrao": ("Acabamento de alto padrão / Porcelanato / Gesso", 0.05),
    "seguranca": ("Sistema de segurança (cerca elétrica, câmeras, portão eletrônico)", 0.02),
    "edicula": ("Edícula / Quarto de empregada", 0.03),
}
TETO_MELHORIAS = 0.25

# Padrão construtivo (classificação simplificada inspirada na NBR 12721 / NBR 14653)
PADROES = ["Baixo", "Normal", "Alto"]
PADRAO_DESC = {
    "Baixo": "Acabamento simples: piso cerâmico comum, sem forro ou forro de PVC, esquadrias de ferro/alumínio simples.",
    "Normal": "Acabamento médio: cerâmica/porcelanato comum, forro de gesso parcial, esquadrias de alumínio.",
    "Alto": "Acabamento superior: porcelanato grande formato, gesso/sancas, projeto arquitetônico, materiais nobres.",
}


@dataclass
class Imovel:
    bairro: str
    tipo: str
    area_construida: float
    quartos: int
    banheiros: int
    largura: float = 0.0
    comprimento: float = 0.0
    area_terreno: float = 0.0
    vagas: int | None = None
    cep: str = ""
    logradouro: str = ""
    regiao: str | None = None
    padrao: str = "Normal"
    vizinhos: list[str] = field(default_factory=list)
    melhorias: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Solicitante:
    nome: str
    cpf: str
    telefone: str
    email: str
    aceite_lgpd: bool = False


@dataclass
class Amostra:
    fonte: str
    bairro: str
    tipo: str
    preco: float
    area_construida: float
    area_terreno: float = 0.0
    quartos: int = 0
    banheiros: int = 0
    vagas: int = 0
    url: str = ""
    simulada: bool = False
    padrao: str = ""  # "" = não identificado no anúncio
    titulo: str = ""

    @property
    def preco_m2(self) -> float:
        return self.preco / self.area_construida if self.area_construida else 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["preco_m2"] = round(self.preco_m2, 2)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Amostra":
        keys = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in keys})
