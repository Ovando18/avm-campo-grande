"""Validações e máscaras: CPF, telefone, CEP, e-mail."""
from __future__ import annotations

import re

DDD_VALIDOS = {
    11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 24, 27, 28, 31, 32, 33, 34, 35, 37, 38, 41, 42, 43, 44, 45, 46,
    47, 48, 49, 51, 53, 54, 55, 61, 62, 63, 64, 65, 66, 67, 68, 69, 71, 73, 74, 75, 77, 79, 81, 82, 83, 84, 85,
    86, 87, 88, 89, 91, 92, 93, 94, 95, 96, 97, 98, 99,
}
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def validar_cpf(cpf: str) -> bool:
    d = digits(cpf)
    if len(d) != 11 or d == d[0] * 11:
        return False
    for pos in (9, 10):
        soma = sum(int(d[i]) * (pos + 1 - i) for i in range(pos))
        dv = (soma * 10) % 11 % 10
        if dv != int(d[pos]):
            return False
    return True


def formatar_cpf(cpf: str) -> str:
    d = digits(cpf)
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:11]}" if len(d) == 11 else cpf


def validar_telefone(tel: str) -> bool:
    d = digits(tel)
    if len(d) not in (10, 11) or int(d[:2]) not in DDD_VALIDOS:
        return False
    if len(d) == 11 and d[2] != "9":
        return False
    return True


def formatar_telefone(tel: str) -> str:
    d = digits(tel)
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return tel


def validar_email(email: str) -> bool:
    return bool(EMAIL_RE.match((email or "").strip()))


def formatar_cep(cep: str) -> str:
    d = digits(cep)
    return f"{d[:5]}-{d[5:]}" if len(d) == 8 else cep


def cep_faixa_campo_grande(cep: str) -> bool:
    """Faixa postal dos Correios para Campo Grande/MS: 79000-001 a 79124-999."""
    d = digits(cep)
    return len(d) == 8 and 79000001 <= int(d) <= 79124999
