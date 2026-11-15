import os

os.environ["AVM_FORCE_MOCK"] = "true"

import pytest  # noqa: E402

from avm import bairros as B  # noqa: E402
from avm.collector import Coletor  # noqa: E402
from avm.config import Settings  # noqa: E402
from avm.engine import fator_melhorias, fator_terreno, filtrar_similares, sanear_iqr, avaliar  # noqa: E402
from avm.models import Amostra, Imovel, Solicitante  # noqa: E402
from avm.pdf_report import gerar_pdf  # noqa: E402
from avm.scraper import _num  # noqa: E402
from avm.validators import cep_faixa_campo_grande, validar_cpf, validar_email, validar_telefone  # noqa: E402


def _settings(tmp_path):
    os.environ["CACHE_DB_PATH"] = str(tmp_path / "c.sqlite3")
    return Settings()


def _imovel(**kw):
    base = dict(bairro="Jardim dos Estados", tipo="Casa Térrea", area_construida=180, quartos=3, banheiros=2,
                largura=12, comprimento=30, area_terreno=360, regiao="Centro")
    base.update(kw)
    return Imovel(**base)


def test_validadores():
    assert validar_cpf("529.982.247-25")
    assert not validar_cpf("111.111.111-11")
    assert not validar_cpf("529.982.247-24")
    assert validar_telefone("(67) 99999-0000")
    assert not validar_telefone("(67) 89999-0000")
    assert validar_email("a.b@empresa.com.br") and not validar_email("x@y")
    assert cep_faixa_campo_grande("79002-000") and not cep_faixa_campo_grande("78000-000")


def test_bairros_e_fallback():
    assert B.resolver("carandá bosque") == "Carandá"
    assert B.regiao_de("Tiradentes") == "Bandeira"
    niveis = B.niveis_fallback("Rita Vieira")
    assert niveis[0][1] == ["Rita Vieira"] and "Bandeira" in niveis[1][0]
    assert len(niveis[-1][1]) == len(B.todos_bairros())


def test_num_br():
    assert _num("R$ 1.250.000") == 1250000
    assert _num("120m²") == 120
    assert _num("1.250,50") == 1250.5
    assert _num([95]) == 95


def test_filtro_similaridade():
    im = _imovel()
    a = [Amostra("x", "b", "t", 900000, 180, quartos=3), Amostra("x", "b", "t", 900000, 260, quartos=3),
         Amostra("x", "b", "t", 900000, 150, quartos=5)]
    assert len(filtrar_similares(a, im)) == 1


def test_iqr_remove_outliers():
    vals = [5000, 5100, 5200, 5300, 5400, 5500, 1500, 16000]
    a = [Amostra("x", "b", "t", v * 100, 100) for v in vals]
    keep, drop, _ = sanear_iqr(a)
    assert {round(x.preco_m2) for x in drop} == {1500, 16000} and len(keep) == 6


def test_fatores():
    soma, _ = fator_melhorias(list(["piscina", "gourmet", "armarios", "solar", "alto_padrao", "seguranca", "edicula"]))
    assert soma == pytest.approx(0.25)
    amostras = [Amostra("x", "b", "t", 1, 100, area_terreno=300) for _ in range(5)]
    assert fator_terreno(_imovel(area_terreno=330), amostras)[0] == 1.0
    assert fator_terreno(_imovel(area_terreno=1200), amostras)[0] == pytest.approx(1.15)
    assert fator_terreno(_imovel(tipo="Apartamento"), amostras)[0] == 1.0


def test_fluxo_completo_mock_e_pdf(tmp_path):
    s = _settings(tmp_path)
    im = _imovel(melhorias=["piscina", "solar"])
    res = avaliar(im, Coletor(s), "529.982.247-25")
    assert res.simulado and res.n_saneadas >= 5
    assert res.valor_minimo < res.valor_final < res.valor_maximo
    esperado = res.mediana_unit * im.area_construida * res.fator_terreno * 1.10
    assert res.valor_final == pytest.approx(esperado, rel=1e-6)
    assert res.protocolo.startswith("AVM-CG-")
    pdf = gerar_pdf(im, Solicitante("Fulano de Tal", "529.982.247-25", "(67) 99999-0000", "f@x.com", True), res, s)
    assert pdf[:4] == b"%PDF" and len(pdf) > 5000


def test_fallback_geografico(tmp_path):
    s = _settings(tmp_path)
    res = avaliar(_imovel(bairro="Núcleo Industrial", regiao="Imbirussu", area_construida=70, quartos=2), Coletor(s))
    assert res.n_saneadas >= 3
