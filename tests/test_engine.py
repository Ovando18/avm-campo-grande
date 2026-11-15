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


def test_bairros_e_niveis():
    assert B.oficial("carandá bosque") == "Carandá"
    assert B.regiao_de("Tiradentes") == "Bandeira"
    assert "Água Limpa Park" in B.opcoes_select()
    assert B.mesmo_bairro("Agua Limpa Park", "Jardim Água Limpa Park")
    assert not B.mesmo_bairro("Água Limpa Park", "Seminário")
    niveis = B.niveis_pesquisa("Água Limpa Park", ["Seminário", "Vila Nasser"], "Segredo")
    assert [n[2] for n in niveis] == ["bairro", "vizinhos"] and niveis[0][1] == ["Água Limpa Park"]
    niveis = B.niveis_pesquisa("Rita Vieira", [], None)
    assert niveis[1][2] == "regiao" and "Bandeira" in niveis[1][0]


def test_num_br():
    assert _num("R$ 1.250.000") == 1250000
    assert _num("120m²") == 120
    assert _num("1.250,50") == 1250.5
    assert _num([95]) == 95


def test_filtro_mesmo_padrao():
    im = _imovel(padrao="Alto")
    a = [Amostra("x", "b", "t", 900000, 180, quartos=3, padrao="Alto"), Amostra("x", "b", "t", 900000, 260, quartos=3),
         Amostra("x", "b", "t", 900000, 150, quartos=5), Amostra("x", "b", "t", 900000, 180, quartos=3, padrao="Baixo"),
         Amostra("x", "b", "t", 900000, 180, quartos=3, banheiros=6), Amostra("x", "b", "t", 900000, 170, quartos=2)]
    assert len(filtrar_similares(a, im)) == 2  # padrão Alto + padrão não identificado


def test_iqr_remove_outliers():
    vals = [5000, 5100, 5200, 5300, 5400, 5500, 1500, 16000]
    a = [Amostra("x", "b", "t", v * 100, 100) for v in vals]
    keep, drop, _ = sanear_iqr(a)
    assert {round(x.preco_m2) for x in drop} == {1500, 16000} and len(keep) == 6


def test_fatores():
    soma, _ = fator_melhorias(list(["piscina", "gourmet", "armarios", "solar", "alto_padrao", "seguranca", "edicula"]))
    assert soma == pytest.approx(0.25)
    soma, _ = fator_melhorias(["alto_padrao", "piscina"], padrao="Alto")
    assert soma == pytest.approx(0.06)
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


def test_prioriza_mesmo_bairro(tmp_path):
    s = _settings(tmp_path)
    res = avaliar(_imovel(bairro="Água Limpa Park", regiao="Segredo", vizinhos=["Seminário"], padrao="Alto"), Coletor(s))
    assert res.n_saneadas >= 3
    assert set(res.amostras["padrao"]) <= {"Alto", ""}
    if res.nivel_tipo == "bairro":
        assert set(res.amostras["bairro"]) == {"Água Limpa Park"}
    else:
        assert set(res.amostras["bairro"]) <= {"Água Limpa Park", "Seminário"}


def test_vizinhos_so_quando_falta(tmp_path, monkeypatch):
    from avm import mock

    s = _settings(tmp_path)
    original = mock.gerar_bairro

    def poucos(bairro, *a, **kw):  # bairro do avaliando com só 2 anúncios
        if bairro == "Água Limpa Park":
            kw["n"] = 2
        return original(bairro, *a, **kw)

    monkeypatch.setattr(mock, "gerar_bairro", poucos)
    res = avaliar(_imovel(bairro="Água Limpa Park", regiao="Segredo", vizinhos=["Seminário", "Vila Nasser", "Nova Lima"]), Coletor(s))
    assert res.nivel_tipo == "vizinhos"
    assert set(res.amostras["bairro"]) <= {"Água Limpa Park", "Seminário", "Vila Nasser", "Nova Lima"}


def test_extrator_generico():
    from avm.extract import extrair_anuncios

    # HTML sintético (formato hipotético) — cobre JSON-LD e cartões
    jsonld = """<script type="application/ld+json">{"@type":"ItemList","itemListElement":[
      {"@type":"SingleFamilyResidence","name":"Casa alto padrão com piscina e gourmet","url":"/imovel/1",
       "floorSize":{"value":"210"},"numberOfBedrooms":4,"address":{"neighborhood":"Água Limpa Park"},
       "offers":{"price":"1.150.000,00"}}]}</script>"""
    assert extrair_anuncios(jsonld, "https://www.infoimoveis.com.br/")[0]["preco"] == 1150000
    cards = """<div class="card"><a href="/imovel/2">Casa à venda</a><span>R$ 650.000</span>
      <span>150 m²</span><span>360 m²</span><span>3 quartos</span><span>2 banheiros</span><span>2 vagas</span></div>"""
    it = extrair_anuncios(cards, "https://www.infoimoveis.com.br/")[0]
    assert (it["preco"], it["area_construida"], it["area_terreno"], it["quartos"]) == (650000, 150, 360, 3)
    assert it["url"] == "https://www.infoimoveis.com.br/imovel/2"


def test_extrator_payload_nextjs():
    """Formato do payload público do Infoimóveis (Next.js RSC), com dados fictícios."""
    import json

    from avm.extract import extrair_anuncios

    dados = [{"id": 111, "valor": 890000, "finalidade": "Venda", "tipo": "Casa-Térrea", "cidade": "Campo Grande",
              "bairro": "Água Limpa Park", "estado": "MS", "area_construida": "210,00"},
             {"id": 222, "valor": 3500, "finalidade": "Aluguel", "tipo": "Casa-Térrea", "cidade": "Campo Grande",
              "bairro": "Centro", "estado": "MS", "area_construida": "120,00"}]
    chunk = '3:["$","div",null,{"data":' + json.dumps(dados, ensure_ascii=False) + "}]"
    html = "<script>self.__next_f.push([1," + json.dumps(chunk) + "])</script>"
    it = extrair_anuncios(html, "https://www.infoimoveis.com.br/")
    assert len(it) == 1 and it[0]["preco"] == 890000 and it[0]["area_construida"] == 210
    assert it[0]["url"] == "https://www.infoimoveis.com.br/imovel/venda-casa-terrea-ms-campo-grande-agua-limpa-park/111"
