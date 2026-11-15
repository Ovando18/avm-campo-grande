"""AVM Campo Grande/MS — Avaliação Automatizada de Imóveis (Streamlit)."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


def _recarregar_avm_se_alterado() -> None:
    """O Streamlit reexecuta este script a cada atualização do repositório, mas mantém em memória os módulos
    já importados. Se os arquivos do pacote `avm` mudaram (ex.: após um git push), descarta a versão antiga
    para que a nova seja importada — evita ImportError por mistura de versões."""
    raiz = Path(__file__).resolve().parent
    arquivos = list((raiz / "avm").glob("*.py")) + list((raiz / "data").glob("*.json"))
    carimbo = max((f.stat().st_mtime for f in arquivos), default=0.0)
    pkg = sys.modules.get("avm")
    if pkg is not None and getattr(pkg, "_carimbo", None) != carimbo:
        for nome in [m for m in sys.modules if m == "avm" or m.startswith("avm.")]:
            del sys.modules[nome]
    import avm

    avm._carimbo = carimbo


_recarregar_avm_se_alterado()

from avm import bairros as B  # noqa: E402
from avm.cep import consultar_cep  # noqa: E402
from avm.collector import Coletor  # noqa: E402
from avm.config import get_settings  # noqa: E402
from avm.engine import AmostrasInsuficientes, avaliar  # noqa: E402
from avm.models import MELHORIAS, PADRAO_DESC, PADROES, TIPOS, Imovel, Solicitante  # noqa: E402
from avm.pdf_report import brl, gerar_pdf, num  # noqa: E402
from avm.validators import (  # noqa: E402
    digits,
    formatar_cep,
    formatar_cpf,
    formatar_telefone,
    validar_cpf,
    validar_email,
    validar_telefone,
)

st.set_page_config(page_title="AVM Campo Grande/MS", page_icon="🏠", layout="wide", initial_sidebar_state="collapsed")
settings = get_settings()

st.markdown(
    """
<style>
:root { --navy:#0F2A44; --teal:#0E7C66; --muted:#5B6770; }
.block-container { max-width: 1100px; padding-top: 1.6rem; }
.hero h1 { font-size: 1.65rem; margin: 0; color: var(--navy); letter-spacing: -.01em; }
.hero p { color: var(--muted); margin: .2rem 0 1rem; }
.stepper { display:flex; gap:.5rem; margin: .4rem 0 1.4rem; flex-wrap: wrap; }
.step { flex:1; min-width: 150px; border-radius: 10px; padding: .55rem .8rem; background:#EEF2F5; color:#5B6770; font-size:.86rem; }
.step b { display:block; font-size:.72rem; text-transform:uppercase; letter-spacing:.06em; }
.step.on { background: var(--navy); color:#fff; }
.step.done { background:#DDF1EC; color: var(--teal); }
.valor-card { background: var(--navy); color:#fff; border-radius: 14px; padding: 1.3rem 1.5rem; }
.valor-card small { color:#CFE3F5; text-transform: uppercase; letter-spacing:.07em; font-size:.72rem; }
.valor-card .v { font-size: 2.3rem; font-weight: 700; line-height:1.15; margin:.25rem 0; }
.valor-card .r { color:#CFE3F5; font-size:.92rem; }
.area-pill { background:#DDF1EC; color:#0E7C66; border-radius:8px; padding:.55rem .8rem; font-weight:600; margin-top:1.75rem; }
@media (prefers-color-scheme: dark) {
  .hero h1 { color:#E6EEF5; } .step { background:#1E2a36; color:#A9B7C3; }
  .area-pill, .step.done { background:#123d35; color:#7FD8C3; }
}
</style>
""",
    unsafe_allow_html=True,
)

SS = st.session_state
SS.setdefault("step", 1)
SS.setdefault("saved", {})
SS.setdefault("resultado", None)

STEP1_KEYS = ["bairro_sel", "regiao", "vizinhos", "padrao", "cep", "tipo", "largura", "comprimento", "irregular",
              "area_manual", "area_construida", "quartos", "banheiros", "vagas"] + [f"m_{k}" for k in MELHORIAS]
STEP2_KEYS = ["nome", "cpf", "telefone", "email", "lgpd"]


def restore(keys):
    for k in keys:
        if k not in SS and k in SS.saved:
            SS[k] = SS.saved[k]


def snapshot(keys):
    for k in keys:
        if k in SS:
            SS.saved[k] = SS[k]


def go(step: int):
    SS.step = step


def stepper():
    labels = [("Etapa 1", "Imóvel avaliando"), ("Etapa 2", "Dados do solicitante"), ("Etapa 3", "Resultado e laudo")]
    html = "".join(
        f'<div class="step {"on" if i + 1 == SS.step else "done" if i + 1 < SS.step else ""}"><b>{a}</b>{b}</div>'
        for i, (a, b) in enumerate(labels)
    )
    st.markdown(f'<div class="stepper">{html}</div>', unsafe_allow_html=True)


st.markdown(
    '<div class="hero"><h1>Avaliação Automatizada de Imóveis · Campo Grande/MS</h1>'
    "<p>Método comparativo com ofertas online, saneamento estatístico (IQR) e mediana homogeneizada — inspirado na ABNT NBR 14653.</p></div>",
    unsafe_allow_html=True,
)
stepper()


# ============================================================================ ETAPA 1
def etapa1():
    restore(STEP1_KEYS)
    SS.setdefault("tipo", TIPOS[0])
    SS.setdefault("quartos", "3")
    SS.setdefault("banheiros", "2")
    SS.setdefault("vagas", "2")

    with st.container(border=True):
        st.subheader("📍 Localização")
        c1, c2 = st.columns([3, 2])
        with c1:
            st.selectbox(
                "Bairro *", B.opcoes_select(), index=None, accept_new_options=True, key="bairro_sel",
                placeholder="Digite o bairro (ex.: Água Limpa Park)",
                help="Bairros oficiais e nomes usados pelos portais (loteamentos). Se o seu não aparecer, "
                     "digite o nome e pressione Enter — ele será usado na pesquisa.",
            )
            sel = SS.get("bairro_sel")
            if sel and SS.get("_bairro_ant") != sel:  # bairro mudou: sugere a região
                SS._bairro_ant = sel
                SS.regiao = B.regiao_de(B.interpretar(sel))
            if sel:
                interp = B.interpretar(sel)
                of = B.oficial(interp)
                if interp != sel:
                    st.caption(f"Interpretado como **{interp}**.")
                if of and B.chave(of) != B.chave(interp):
                    st.caption(f"Pertence ao bairro oficial **{of}**.")
                elif not of and interp not in B.comerciais():
                    st.caption("Bairro fora da base — será pesquisado pelo nome digitado.")
        with c2:
            st.selectbox("Região urbana", B.regioes(), index=None, key="regiao", placeholder="Selecione",
                         help="Usada apenas se os bairros vizinhos não forem informados.")
        sel = SS.get("bairro_sel")
        st.multiselect(
            "Bairros vizinhos (usados somente se não houver imóveis suficientes do mesmo padrão no seu bairro)",
            [b for b in B.opcoes_select() if not sel or B.chave(b) != B.chave(sel)],
            accept_new_options=True, key="vizinhos", placeholder="Escolha ou digite os bairros que fazem divisa…",
        )
        c1, c2 = st.columns([3, 2])
        with c2:
            st.text_input("CEP (opcional)", key="cep", placeholder="79000-000", max_chars=9)
            cep = SS.get("cep", "")
            if digits(cep):
                if SS.get("_cep_checked") != digits(cep):
                    SS._cep_res = consultar_cep(cep)
                    SS._cep_checked = digits(cep)
                r = SS._cep_res
                (st.success if r.ok else st.error)(r.mensagem + (f" {r.logradouro}" if r.logradouro else ""), icon="✅" if r.ok else "⚠️")
                if r.ok and r.bairro and not SS.get("bairro_sel"):
                    st.caption(f"Bairro segundo os Correios: {r.bairro}")
        st.radio("Tipo de imóvel *", TIPOS, key="tipo", horizontal=True)
        SS.setdefault("padrao", "Normal")
        st.radio("Padrão construtivo *", PADROES, key="padrao", horizontal=True,
                 help="A comparação usa apenas imóveis do mesmo padrão. " + " ".join(f"{k}: {v}" for k, v in PADRAO_DESC.items()))
        st.caption(PADRAO_DESC[SS.padrao])

    with st.container(border=True):
        st.subheader("📐 Dimensões e tipologia")
        apto = SS.tipo == "Apartamento"
        c1, c2, c3 = st.columns(3)
        c1.number_input("Largura / Testada (m)" + ("" if apto else " *"), min_value=0.0, max_value=500.0, step=0.5, key="largura")
        c2.number_input("Comprimento / Profundidade (m)" + ("" if apto else " *"), min_value=0.0, max_value=1000.0, step=0.5, key="comprimento")
        area_calc = (SS.get("largura") or 0) * (SS.get("comprimento") or 0)
        c3.markdown(f'<div class="area-pill">Área do terreno: {num(area_calc)} m²</div>', unsafe_allow_html=True)
        if apto:
            st.caption("Para apartamentos as dimensões do terreno são opcionais (o fator terreno não é aplicado).")
        st.checkbox("Terreno irregular — ajustar a área total manualmente", key="irregular")
        if SS.get("irregular"):
            if not SS.get("area_manual"):
                SS.area_manual = float(area_calc)
            st.number_input("Área total do terreno ajustada (m²)", min_value=0.0, max_value=500000.0, step=1.0, key="area_manual")

        st.number_input("Área construída (m²) *", min_value=0.0, max_value=5000.0, step=1.0, key="area_construida")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.segmented_control("Quartos *", ["1", "2", "3", "4", "5+"], key="quartos")
        with c2:
            st.segmented_control("Banheiros *", ["1", "2", "3", "4", "5+"], key="banheiros")
        with c3:
            st.segmented_control("Vagas de garagem", ["0", "1", "2", "3", "4+"], key="vagas")

    with st.container(border=True):
        st.subheader("✨ Melhorias e benfeitorias")
        cols = st.columns(2)
        for i, (k, (nome, pct)) in enumerate(MELHORIAS.items()):
            with cols[i % 2].container(border=True):
                st.checkbox(f"{nome}", key=f"m_{k}", help=f"Valorização técnica de +{pct * 100:.0f}% sobre o valor base")
                st.caption(f"+{pct * 100:.0f}% sobre o valor base")
        soma = sum(MELHORIAS[k][1] for k in MELHORIAS if SS.get(f"m_{k}"))
        st.caption(f"Valorização total por melhorias: **+{min(soma, .25) * 100:.0f}%** (teto técnico de +25%)")

    snapshot(STEP1_KEYS)

    if st.button("Avançar para dados do solicitante →", type="primary", use_container_width=True):
        erros = []
        sel = SS.get("bairro_sel")
        if not sel or not sel.strip():
            erros.append("Informe o bairro.")
        elif not SS.get("vizinhos") and not SS.get("regiao"):
            erros.append("Informe os bairros vizinhos ou a região urbana (usados se faltarem amostras no seu bairro).")
        if digits(SS.get("cep", "")):
            cep_r = SS.get("_cep_res")
            if not cep_r or not cep_r.ok:
                erros.append("CEP inválido ou fora de Campo Grande/MS (deixe em branco se não souber).")
        area_t = SS.area_manual if SS.get("irregular") else area_calc
        if not apto and area_t <= 0:
            erros.append("Informe largura e comprimento do terreno (ou a área ajustada).")
        if (SS.get("area_construida") or 0) < 15:
            erros.append("Área construída deve ser de pelo menos 15 m².")
        if not apto and area_t and SS.area_construida > area_t * 4:
            erros.append("Área construída incompatível com a área do terreno (mais de 4× o terreno).")
        if not SS.get("quartos") or not SS.get("banheiros"):
            erros.append("Selecione quartos e banheiros.")
        if erros:
            for e in erros:
                st.error(e)
            return
        bairro = B.interpretar(sel)
        vizinhos = list(dict.fromkeys(B.interpretar(v) for v in SS.get("vizinhos") or []))
        cep_res = SS.get("_cep_res")
        SS.imovel = Imovel(
            bairro=bairro, regiao=SS.get("regiao"), tipo=SS.tipo, padrao=SS.padrao, vizinhos=vizinhos,
            area_construida=float(SS.area_construida),
            quartos=int(SS.quartos.rstrip("+")), banheiros=int(SS.banheiros.rstrip("+")),
            vagas=int(SS.vagas.rstrip("+")) if SS.get("vagas") else None,
            largura=float(SS.largura or 0), comprimento=float(SS.comprimento or 0), area_terreno=float(area_t or 0),
            cep=formatar_cep(SS.cep) if digits(SS.get("cep", "")) else "",
            logradouro=cep_res.logradouro if cep_res and cep_res.ok else "",
            melhorias=[k for k in MELHORIAS if SS.get(f"m_{k}")],
        )
        go(2)
        st.rerun()


# ============================================================================ ETAPA 2
def etapa2():
    restore(STEP2_KEYS)
    im: Imovel = SS.imovel
    st.info(f"Imóvel: **{im.tipo}** padrão {im.padrao} · {im.bairro} ({im.regiao or '—'}) · {num(im.area_construida)} m² construídos · {im.quartos} quarto(s)", icon="🏠")
    with st.container(border=True):
        st.subheader("👤 Dados do solicitante (para emissão do laudo)")
        st.text_input("Nome completo *", key="nome", max_chars=120)
        c1, c2 = st.columns(2)
        c1.text_input("CPF *", key="cpf", placeholder="000.000.000-00", max_chars=14)
        c2.text_input("Telefone / WhatsApp *", key="telefone", placeholder="(67) 90000-0000", max_chars=16)
        cpf, tel = SS.get("cpf", ""), SS.get("telefone", "")
        if digits(cpf):
            (c1.caption("✅ " + formatar_cpf(cpf)) if validar_cpf(cpf) else c1.caption("⚠️ CPF inválido (dígitos verificadores)"))
        if digits(tel):
            (c2.caption("✅ " + formatar_telefone(tel)) if validar_telefone(tel) else c2.caption("⚠️ Telefone inválido"))
        st.text_input("E-mail *", key="email", placeholder="nome@exemplo.com.br")
        st.checkbox(
            "Autorizo o tratamento dos meus dados pessoais, nos termos da LGPD (Lei nº 13.709/2018), exclusivamente para a "
            "emissão deste parecer técnico de avaliação. *",
            key="lgpd",
        )
    snapshot(STEP2_KEYS)

    b1, b2 = st.columns([1, 2])
    if b1.button("← Voltar", use_container_width=True):
        go(1)
        st.rerun()
    if b2.button("Pesquisar mercado e calcular avaliação", type="primary", use_container_width=True):
        erros = []
        if len((SS.get("nome") or "").split()) < 2:
            erros.append("Informe o nome completo (nome e sobrenome).")
        if not validar_cpf(cpf):
            erros.append("CPF inválido.")
        if not validar_telefone(tel):
            erros.append("Telefone inválido — use DDD + número, ex.: (67) 99999-0000.")
        if not validar_email(SS.get("email", "")):
            erros.append("E-mail inválido.")
        if not SS.get("lgpd"):
            erros.append("É necessário o aceite LGPD para emitir o parecer.")
        if erros:
            for e in erros:
                st.error(e)
            return
        SS.solicitante = Solicitante(SS.nome.strip(), formatar_cpf(cpf), formatar_telefone(tel), SS.email.strip(), True)
        with st.status("Pesquisando ofertas em portais imobiliários de Campo Grande/MS…", expanded=True) as status:
            st.write(f"Bairro-alvo: {im.bairro} · tipo: {im.tipo}")
            try:
                coletor = Coletor(settings)
                res = avaliar(im, coletor, SS.solicitante.cpf)
            except AmostrasInsuficientes as exc:
                status.update(label="Amostras insuficientes", state="error")
                st.error(str(exc))
                for fonte, motivo in coletor.status.falhas.items():
                    st.caption(f"Fonte {fonte} indisponível: {motivo}")
                return
            except Exception as exc:
                status.update(label="Falha na coleta", state="error")
                st.error(f"Não foi possível concluir a avaliação: {exc}")
                return
            for a in res.avisos:
                st.write("↪ " + a)
            st.write(f"{res.n_saneadas} amostras saneadas em: {res.nivel_geografico}")
            status.update(label="Avaliação concluída", state="complete")
        SS.resultado = res
        SS.pdf = None
        go(3)
        st.rerun()


# ============================================================================ ETAPA 3
def etapa3():
    res = SS.resultado
    im: Imovel = SS.imovel
    sol: Solicitante = SS.solicitante
    if res.simulado:
        st.warning(
            "**Modo demonstração:** os portais imobiliários não responderam (offline/bloqueio). Os valores abaixo usam "
            "amostras **simuladas** apenas para testar o fluxo e o PDF — não utilize como estimativa real.",
            icon="🧪",
        )
    if res.status.falhas:
        with st.expander(f"Situação das fontes de pesquisa ({len(res.status.falhas)} indisponível(is))"):
            for fonte, motivo in res.status.falhas.items():
                st.caption(f"**{fonte}** — {motivo}")
            if res.status.fontes_ok:
                st.caption("Fontes com resultados: " + ", ".join(res.status.fontes_ok))

    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown(
            f'<div class="valor-card"><small>Valor estimado de mercado · mediana homogeneizada</small>'
            f'<div class="v">{brl(res.valor_final)}</div>'
            f'<div class="r">Faixa de confiança: {brl(res.valor_minimo)} — {brl(res.valor_maximo)} (±10%)</div>'
            f'<div class="r" style="margin-top:.4rem">Protocolo <b>{res.protocolo}</b> · {res.emitido_em:%d/%m/%Y %H:%M}</div></div>',
            unsafe_allow_html=True,
        )
    with c2:
        m1, m2 = st.columns(2)
        m1.metric("R$/m² construído", brl(res.m2_construido))
        m2.metric("R$/m² terreno", brl(res.m2_terreno) if res.m2_terreno else "—")
        m1.metric("Amostras saneadas", f"{res.n_saneadas} de {res.n_similares}")
        m2.metric("Coef. de variação", f"{res.cv_unit * 100:.1f}%")

    with st.container(border=True):
        st.markdown("**Memória de cálculo**")
        a, b, c, d = st.columns(4)
        a.metric("Mediana R$/m²", brl(res.mediana_unit))
        b.metric("Valor base", brl(res.valor_base))
        c.metric("Fator terreno", num(res.fator_terreno, 3))
        d.metric("Melhorias", f"+{res.soma_melhorias * 100:.0f}%")
        st.caption(
            f"Valor = {brl(res.valor_base)} × {num(res.fator_terreno, 3)} × {num(1 + res.soma_melhorias, 3)} = **{brl(res.valor_final)}** · "
            f"Abrangência: {res.nivel_geografico} · Modo de coleta: {res.status.modo}"
        )
        for av in res.avisos:
            st.caption("↪ " + av)

    st.subheader("Amostras utilizadas")
    st.caption(
        ("✅ Todas as amostras são do **mesmo bairro** do imóvel." if res.nivel_tipo == "bairro"
         else f"ℹ️ O bairro não tinha imóveis suficientes do mesmo padrão; pesquisa ampliada para: {res.nivel_geografico}.")
        + " Critério: mesmo tipo e padrão construtivo, área ±30%, quartos ±1, banheiros ±1."
    )
    df = res.amostras.copy()
    df["area_construida"] = df["area_construida"].map(lambda v: num(v, 1))
    df["area_terreno"] = df["area_terreno"].map(lambda v: num(v, 0) if v else "—")
    df["preco"] = df["preco"].map(brl)
    df["preco_m2"] = df["preco_m2"].map(brl)
    df["padrao"] = df["padrao"].replace("", "não ident.")
    df["url"] = df["url"].where(~df["simulada"].astype(bool), "")
    st.dataframe(
        df[["bairro", "padrao", "area_construida", "area_terreno", "quartos", "preco", "preco_m2", "fonte", "url"]],
        hide_index=True, use_container_width=True,
        column_config={
            "bairro": "Bairro", "padrao": "Padrão", "area_construida": "Á. construída (m²)", "area_terreno": "Á. terreno (m²)",
            "quartos": "Quartos", "preco": "Preço anunciado", "preco_m2": "R$/m²", "fonte": "Fonte",
            "url": st.column_config.LinkColumn("Origem", display_text="abrir anúncio"),
        },
    )
    if len(res.outliers):
        with st.expander(f"Outliers removidos no saneamento ({len(res.outliers)})"):
            lo, hi = res.limites_iqr
            st.caption(f"Faixa aceita de R$/m² (IQR e 50%–150% da mediana): {brl(lo)} a {brl(hi)}")
            od = res.outliers[["bairro", "area_construida", "preco", "preco_m2", "fonte"]].copy()
            od["preco"], od["preco_m2"] = od["preco"].map(brl), od["preco_m2"].map(brl)
            st.dataframe(od, hide_index=True, use_container_width=True)

    if SS.get("pdf") is None:
        SS.pdf = gerar_pdf(im, sol, res, settings)
    b1, b2, b3 = st.columns([2, 1, 1])
    b1.download_button("⬇️ Baixar Laudo de Avaliação (.PDF)", SS.pdf, file_name=f"{res.protocolo}.pdf",
                       mime="application/pdf", type="primary", use_container_width=True)
    if b2.button("← Editar dados", use_container_width=True):
        go(1)
        st.rerun()
    if b3.button("Nova avaliação", use_container_width=True):
        for k in list(SS.keys()):
            del SS[k]
        st.rerun()


{1: etapa1, 2: etapa2, 3: etapa3}[SS.step]()

st.divider()
st.caption(
    "Estimativa estatística baseada em ofertas online vigentes no mercado de Campo Grande/MS. Não substitui laudo com vistoria "
    "presencial (ABNT NBR 14653) para fins judiciais ou garantias bancárias."
)
