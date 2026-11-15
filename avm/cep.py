"""Consulta ViaCEP com validação de município (Campo Grande/MS) e fallback por faixa postal."""
from __future__ import annotations

from dataclasses import dataclass

import requests

from .validators import cep_faixa_campo_grande, digits, formatar_cep


@dataclass
class CepResult:
    ok: bool
    mensagem: str
    logradouro: str = ""
    bairro: str = ""
    online: bool = True


def consultar_cep(cep: str, timeout: int = 6) -> CepResult:
    d = digits(cep)
    if len(d) != 8:
        return CepResult(False, "CEP deve conter 8 dígitos (00000-000).")
    try:
        r = requests.get(f"https://viacep.com.br/ws/{d}/json/", timeout=timeout)
        r.raise_for_status()
        data = r.json()
    except Exception:
        if cep_faixa_campo_grande(d):
            return CepResult(True, f"ViaCEP indisponível — CEP {formatar_cep(d)} aceito pela faixa postal de Campo Grande/MS.", online=False)
        return CepResult(False, "ViaCEP indisponível e o CEP está fora da faixa postal de Campo Grande/MS (79000-001 a 79124-999).", online=False)
    if data.get("erro"):
        return CepResult(False, "CEP não encontrado na base dos Correios.")
    if data.get("uf") != "MS" or data.get("localidade", "").lower() != "campo grande":
        return CepResult(False, f"CEP pertence a {data.get('localidade')}/{data.get('uf')}. Este sistema avalia apenas imóveis em Campo Grande/MS.")
    return CepResult(True, "CEP validado (Campo Grande/MS).", data.get("logradouro", ""), data.get("bairro", ""))
