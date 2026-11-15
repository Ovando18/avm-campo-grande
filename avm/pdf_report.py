"""Laudo / Parecer Técnico de Avaliação em PDF (A4) — template corporativo com ReportLab."""
from __future__ import annotations

import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .config import Settings
from .engine import Resultado
from .models import Imovel, Solicitante
from .validators import formatar_cep, formatar_cpf, formatar_telefone

NAVY = colors.HexColor("#0F2A44")
TEAL = colors.HexColor("#0E7C66")
INK = colors.HexColor("#1F2933")
MUTED = colors.HexColor("#5B6770")
LINE = colors.HexColor("#D5DCE2")
SOFT = colors.HexColor("#F2F5F7")
WARN = colors.HexColor("#B45309")

W, H = A4
MARGIN = 16 * mm


def brl(v: float) -> str:
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def num(v: float, casas: int = 2) -> str:
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _styles():
    ss = getSampleStyleSheet()
    base = dict(fontName="Helvetica", textColor=INK, fontSize=9, leading=12)
    return {
        "h": ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=10.5, textColor=NAVY, spaceBefore=8, spaceAfter=4, leading=13),
        "p": ParagraphStyle("p", **base),
        "small": ParagraphStyle("small", **{**base, "fontSize": 7.5, "leading": 10, "textColor": MUTED}),
        "cell": ParagraphStyle("cell", **{**base, "fontSize": 7.8, "leading": 9.5}),
        "lbl": ParagraphStyle("lbl", **{**base, "fontSize": 7.5, "textColor": MUTED, "leading": 9}),
        "val": ParagraphStyle("val", **{**base, "fontName": "Helvetica-Bold", "fontSize": 9.5}),
        "big": ParagraphStyle("big", fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=colors.white, alignment=TA_CENTER),
        "bigl": ParagraphStyle("bigl", fontName="Helvetica", fontSize=8.5, leading=11, textColor=colors.HexColor("#CFE3F5"), alignment=TA_CENTER),
        "title": ParagraphStyle("title", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=14, textColor=NAVY, spaceAfter=2, leading=17),
        "warn": ParagraphStyle("warn", **{**base, "textColor": WARN, "fontName": "Helvetica-Bold", "fontSize": 8.5}),
    }


def _kv_table(pares: list[tuple[str, str]], st, cols: int = 2) -> Table:
    width = (W - 2 * MARGIN) / cols
    rows, row = [], []
    for lbl, val in pares:
        row.append([Paragraph(lbl.upper(), st["lbl"]), Paragraph(val or "—", st["val"])])
        if len(row) == cols:
            rows.append(row)
            row = []
    if row:
        rows.append(row + [""] * (cols - len(row)))
    t = Table(rows, colWidths=[width] * cols)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def _header_footer(settings: Settings, res: Resultado):
    logo_path = Path(settings.company_logo) if settings.company_logo else None
    has_logo = bool(logo_path and logo_path.is_file())
    emitido = res.emitido_em.strftime("%d/%m/%Y %H:%M")

    def draw(canv, doc):
        canv.saveState()
        top = H - 12 * mm
        canv.setFillColor(NAVY)
        canv.rect(0, H - 6, W, 6, stroke=0, fill=1)
        x = MARGIN
        if has_logo:
            canv.drawImage(str(logo_path), x, top - 14 * mm, width=22 * mm, height=14 * mm, preserveAspectRatio=True, mask="auto")
        else:
            canv.setFillColor(TEAL)
            canv.roundRect(x, top - 13 * mm, 13 * mm, 13 * mm, 2 * mm, stroke=0, fill=1)
            canv.setFillColor(colors.white)
            canv.setFont("Helvetica-Bold", 12)
            initials = "".join(w[0] for w in settings.company_name.split()[:2]).upper()
            canv.drawCentredString(x + 6.5 * mm, top - 8.3 * mm, initials)
        tx = x + (25 * mm if has_logo else 16 * mm)
        canv.setFillColor(NAVY)
        canv.setFont("Helvetica-Bold", 11)
        canv.drawString(tx, top - 4 * mm, settings.company_name)
        canv.setFont("Helvetica", 7.5)
        canv.setFillColor(MUTED)
        canv.drawString(tx, top - 8 * mm, f"CNPJ {settings.company_cnpj}  ·  {settings.company_address}")
        canv.drawString(tx, top - 11.5 * mm, f"{settings.company_phone}  ·  {settings.company_email}")
        canv.setFont("Helvetica-Bold", 9)
        canv.setFillColor(TEAL)
        canv.drawRightString(W - MARGIN, top - 4 * mm, f"Protocolo {res.protocolo}")
        canv.setFont("Helvetica", 7.5)
        canv.setFillColor(MUTED)
        canv.drawRightString(W - MARGIN, top - 8 * mm, f"Emitido em {emitido} (horário de MS)")
        canv.drawRightString(W - MARGIN, top - 11.5 * mm, f"Página {doc.page}")
        canv.setStrokeColor(LINE)
        canv.setLineWidth(0.8)
        canv.line(MARGIN, top - 15.5 * mm, W - MARGIN, top - 15.5 * mm)
        # rodapé
        canv.line(MARGIN, 14 * mm, W - MARGIN, 14 * mm)
        canv.setFont("Helvetica", 6.5)
        canv.drawString(MARGIN, 10 * mm, f"Hash de integridade (SHA-256): {res.hash_integridade}")
        canv.drawString(MARGIN, 7 * mm, "Estimativa estatística automatizada (AVM) — não substitui laudo com vistoria presencial (NBR 14653).")
        if res.simulado:
            canv.setFillColor(WARN)
            canv.setFont("Helvetica-Bold", 7)
            canv.drawRightString(W - MARGIN, 7 * mm, "MODO DEMONSTRAÇÃO — AMOSTRAS SIMULADAS")
        canv.restoreState()

    return draw


def gerar_pdf(imovel: Imovel, solicitante: Solicitante, res: Resultado, settings: Settings) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=34 * mm, bottomMargin=20 * mm,
        title=f"Parecer Técnico de Avaliação {res.protocolo}", author=settings.company_name,
        subject="Avaliação automatizada de imóvel — Campo Grande/MS",
    )
    st = _styles()
    el = []
    el.append(Paragraph("Parecer Técnico de Avaliação Mercadológica", st["title"]))
    el.append(Paragraph(
        "Modelo Automatizado de Avaliação (AVM) — Método Comparativo Direto de Dados de Mercado, "
        "regra da mediana homogeneizada · Município de Campo Grande/MS", st["small"]))
    if res.simulado:
        el.append(Spacer(1, 4))
        el.append(Paragraph(
            "ATENÇÃO: os portais imobiliários não responderam no momento da emissão; este documento foi gerado com "
            "amostras SIMULADAS para fins de demonstração e NÃO possui validade como estimativa de mercado.", st["warn"]))

    # Bloco 1
    el.append(Paragraph("1. Identificação do Solicitante", st["h"]))
    el.append(_kv_table([
        ("Nome completo", solicitante.nome),
        ("CPF", formatar_cpf(solicitante.cpf)),
        ("Telefone / WhatsApp", formatar_telefone(solicitante.telefone)),
        ("E-mail", solicitante.email),
    ], st))

    # Bloco 2
    el.append(Paragraph("2. Caracterização do Imóvel Avaliado", st["h"]))
    if imovel.largura and imovel.comprimento:
        dims = f"{num(imovel.largura)} m × {num(imovel.comprimento)} m = {num(imovel.area_terreno)} m²"
        if abs(imovel.largura * imovel.comprimento - imovel.area_terreno) > 0.01:
            dims = f"{num(imovel.largura)} m × {num(imovel.comprimento)} m (irregular, área ajustada: {num(imovel.area_terreno)} m²)"
    elif imovel.area_terreno:
        dims = f"{num(imovel.area_terreno)} m²"
    else:
        dims = "Não se aplica (fração ideal)"
    melh = "; ".join(n for n, _ in res.melhorias_aplicadas) or "Nenhuma declarada"
    el.append(_kv_table([
        ("Bairro / Região urbana", f"{imovel.bairro} — {imovel.regiao or '—'}"),
        ("CEP / Logradouro", " — ".join(x for x in [formatar_cep(imovel.cep) if imovel.cep else "", imovel.logradouro] if x) or "Não informado"),
        ("Tipo de imóvel / Padrão construtivo", f"{imovel.tipo} · padrão {imovel.padrao}"),
        ("Terreno (testada × profundidade)", dims),
        ("Área construída", f"{num(imovel.area_construida)} m²"),
        ("Quartos / Banheiros / Vagas", f"{imovel.quartos} / {imovel.banheiros} / {imovel.vagas if imovel.vagas is not None else '—'}"),
        ("Bairros vizinhos declarados", ", ".join(imovel.vizinhos) or "Não informados"),
    ], st))
    el.append(Spacer(1, 3))
    el.append(Paragraph(f"<b>Melhorias e benfeitorias declaradas:</b> {melh}", st["p"]))

    # Bloco 3
    el.append(Paragraph("3. Resumo Estatístico e Resultado da Avaliação", st["h"]))
    destaque = Table([[Paragraph("VALOR DE MERCADO ESTIMADO (MEDIANA HOMOGENEIZADA)", st["bigl"])],
                      [Paragraph(brl(res.valor_final), st["big"])],
                      [Paragraph(f"Intervalo de liquidez: {brl(res.valor_minimo)} a {brl(res.valor_maximo)} (±10%)", st["bigl"])]],
                     colWidths=[W - 2 * MARGIN])
    destaque.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    el.append(destaque)
    el.append(Spacer(1, 5))

    faixa = Table([
        ["Mínimo (−10%)", "Médio (mediana)", "Máximo (+10%)", "R$/m² construído", "R$/m² terreno"],
        [brl(res.valor_minimo), brl(res.valor_final), brl(res.valor_maximo), brl(res.m2_construido),
         brl(res.m2_terreno) if res.m2_terreno else "—"],
    ], colWidths=[(W - 2 * MARGIN) / 5] * 5)
    faixa.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica", 7.5), ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
        ("FONT", (0, 1), (-1, 1), "Helvetica-Bold", 9.5), ("TEXTCOLOR", (0, 1), (-1, 1), INK),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE), ("BACKGROUND", (0, 0), (-1, 0), SOFT),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    el.append(faixa)
    el.append(Spacer(1, 5))

    lo, hi = res.limites_iqr
    iqr_txt = f"{brl(lo)} a {brl(hi)}" if lo != float("-inf") else "não aplicado (n < 4)"
    el.append(_kv_table([
        ("Amostras pesquisadas (abrangência)", f"{res.n_pesquisadas}  ·  {res.nivel_geografico}"),
        ("Amostras semelhantes / saneadas", f"{res.n_similares} / {res.n_saneadas}  (outliers removidos: {len(res.outliers)})"),
        ("Mediana do R$/m² (M_unit)", brl(res.mediana_unit)),
        ("Média do R$/m² · Coef. variação", f"{brl(res.media_unit)} · {num(res.cv_unit * 100, 1)}%"),
        ("Valor base (M_unit × área construída)", brl(res.valor_base)),
        ("Faixa de saneamento (IQR e 50–150% da mediana)", iqr_txt),
        ("Fator terreno", f"{num(res.fator_terreno, 3)}" + (f"  (mediana terrenos: {num(res.mediana_terreno_amostras, 0)} m²)" if res.mediana_terreno_amostras else "")),
        ("Fator melhorias", f"1 + {num(res.soma_melhorias * 100, 1)}% (teto 25%)"),
    ], st))
    el.append(Spacer(1, 3))
    el.append(Paragraph(
        f"<b>Fórmula:</b> Valor = V<sub>base</sub> × F<sub>terreno</sub> × (1 + Σ melhorias) = "
        f"{brl(res.valor_base)} × {num(res.fator_terreno, 3)} × {num(1 + res.soma_melhorias, 3)} = <b>{brl(res.valor_final)}</b>",
        st["p"]))

    # Bloco 4
    el.append(Paragraph("4. Quadro Comparativo de Amostras (Mercado Online)", st["h"]))
    head = ["#", "Fonte", "Bairro", "Padrão", "Á. constr.", "Á. terreno", "Qts", "Preço anunciado", "R$/m²", "Origem"]
    rows = [head]
    for i, r in enumerate(res.amostras.itertuples(), 1):
        origem = "simul." if r.simulada else (f'<link href="{r.url}" color="#0E7C66">link</link>' if r.url else "—")
        rows.append([
            str(i), Paragraph(r.fonte, st["cell"]), Paragraph(r.bairro, st["cell"]), r.padrao or "n/i", num(r.area_construida, 1),
            num(r.area_terreno, 0) if r.area_terreno else "—", str(r.quartos or "—"),
            brl(r.preco), brl(r.preco_m2), Paragraph(origem, st["cell"]),
        ])
    cw = [7, 21, 31, 14, 17, 17, 9, 28, 22, 12]
    tab = Table(rows, colWidths=[c * mm for c in cw], repeatRows=1)
    tab.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.3), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("FONT", (0, 1), (-1, -1), "Helvetica", 7.6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SOFT]), ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("ALIGN", (4, 1), (8, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    el.append(tab)
    el.append(Spacer(1, 3))
    fontes = "gerador de amostras simuladas (portais indisponíveis)" if res.simulado else (", ".join(res.status.fontes_ok) or "—")
    el.append(Paragraph(
        f"Fontes consultadas: {fontes} · Modo de coleta: {res.status.modo}. Amostras listadas de forma resumida e anônima "
        f"(sem identificação de proprietários/anunciantes). Critério de comparação: mesmo bairro (bairros vizinhos apenas se "
        f"insuficiente), mesmo tipo e padrão construtivo, área construída ±30%, quartos ±1, banheiros ±1. "
        f"n/i = padrão não identificado no anúncio.",
        st["small"]))
    for a in res.avisos:
        el.append(Paragraph(f"• {a}", st["small"]))

    # Nota técnica
    nota = (
        "<b>Nota técnica e ressalvas.</b> O presente parecer constitui <b>estimativa estatística</b> do valor de mercado, "
        "obtida de forma automatizada a partir de ofertas de venda vigentes em portais imobiliários online para o município "
        "de Campo Grande/MS, tratadas pela regra da mediana com saneamento de outliers (critério IQR) e homogeneização por "
        "fatores de terreno e benfeitorias. Os dados do imóvel avaliando foram declarados pelo solicitante e não foram "
        "verificados in loco. Valores de oferta tendem a superar os valores efetivos de transação. Este documento "
        "<b>não substitui</b> laudo de avaliação com vistoria presencial completa elaborado por profissional habilitado "
        "(CREA/CAU/CRECI-CNAI), conforme ABNT NBR 14653-1 e 14653-2, para fins judiciais, garantias bancárias, "
        "partilhas ou tributários. Dados pessoais tratados conforme a LGPD (Lei nº 13.709/2018), com consentimento do titular, "
        "exclusivamente para emissão deste parecer."
    )
    box = Table([[Paragraph(nota, st["small"])]], colWidths=[W - 2 * MARGIN])
    box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SOFT), ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                             ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                             ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    assin = []
    if settings.responsavel_tecnico:
        assin = [Spacer(1, 18), Paragraph("_" * 48, st["p"]), Paragraph(settings.responsavel_tecnico, st["p"])]
    el.append(Spacer(1, 8))
    el.append(KeepTogether([box] + assin))

    hf = _header_footer(settings, res)
    doc.build(el, onFirstPage=hf, onLaterPages=hf)
    return buf.getvalue()
