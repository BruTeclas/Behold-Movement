#!/usr/bin/env python3
"""Estrutura da planilha de inscrições do Behold Movement.

Abas:
  Inscrições  uma linha por pessoa, preenchida pelo n8n (chave: Telefone)
  Resumo      totais gerais e por ministério (COUNTIF) e rankings por estado,
              cidade e bairro (QUERY, que existe só no Google Sheets)

COLUNAS e resumo_celulas() são a fonte da verdade: o n8n usa os mesmos nomes de
coluna, e as mesmas células são aplicadas na planilha do Google pelo conector.

Uso: python3 scripts/build-planilha.py [saida.xlsx]   (gera um modelo .xlsx)
"""
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

BLUE = "1F5BF2"
INK = "16171C"
PAPER = "ECEAE5"
FONT = "Arial"

# Os nomes das colunas precisam ser iguais aos do workflow do n8n (scripts/build-n8n.py).
COLUNAS = [
    ("ID", 16),
    ("Data/hora", 20),
    ("Nome", 20),
    ("Sobrenome", 24),
    ("Telefone", 17),
    ("E-mail", 30),
    ("CEP", 11),
    ("Endereço", 34),
    ("Bairro", 22),
    ("Cidade", 22),
    ("Estado", 8),
    ("Igreja", 26),
    ("Ministério", 18),
    ("Consentimento", 15),
    ("Status e-mail", 16),
    ("Status WhatsApp", 17),
    ("Conversa Chatwoot", 18),
    ("Observações", 36),
]
COL = {nome: get_column_letter(i + 1) for i, (nome, _) in enumerate(COLUNAS)}
ULTIMA = get_column_letter(len(COLUNAS))

MINISTERIOS = ["Evangelizando", "Mídia", "Suprimento", "Ação social", "Intercessão"]


def rng(nome: str) -> str:
    c = COL[nome]
    return f"'Inscrições'!{c}:{c}"


def query(select: str, vazio: str = "Sem inscrições ainda") -> str:
    """Ranking com QUERY; o IFERROR evita o erro de resultado vazio."""
    tabela = f"'Inscrições'!A:{ULTIMA}"
    return f'=IFERROR(QUERY({tabela}, "{select}", 1), "{vazio}")'


def resumo_celulas() -> dict[str, tuple[str, str]]:
    """Célula -> (valor ou fórmula, estilo). Estilos: titulo, secao, rotulo, valor, nota."""
    nome, estado, cidade, bairro = COL["Nome"], COL["Estado"], COL["Cidade"], COL["Bairro"]
    c: dict[str, tuple[str, str]] = {
        "A1": ("Behold Movement · Inscrições", "titulo"),
        "A3": ("Geral", "secao"), "B3": ("Pessoas", "secao"),
        "A4": ("Total de inscrições", "rotulo"), "B4": (f"=COUNTA({rng('Nome')})-1", "valor"),
        "A5": ("E-mails enviados", "rotulo"), "B5": (f'=COUNTIF({rng("Status e-mail")},"enviado")', "valor"),
        "A6": ("WhatsApp enviados", "rotulo"), "B6": (f'=COUNTIF({rng("Status WhatsApp")},"enviado")', "valor"),
        "A7": ("Envios com erro", "rotulo"),
        "B7": (f'=COUNTIF({rng("Status e-mail")},"erro*")+COUNTIF({rng("Status WhatsApp")},"erro*")', "valor"),
        "A9": ("Por ministério", "secao"), "B9": ("Pessoas", "secao"),
        "D2": ("Por estado", "secao"),
        "D3": (query(f"select {estado}, count({nome}) where {nome} is not null group by {estado} "
                     f"order by count({nome}) desc label {estado} 'Estado', count({nome}) 'Pessoas'"), "valor"),
        "G2": ("Por cidade (25 maiores)", "secao"),
        "G3": (query(f"select {cidade}, {estado}, count({nome}) where {nome} is not null "
                     f"group by {cidade}, {estado} order by count({nome}) desc limit 25 "
                     f"label {cidade} 'Cidade', {estado} 'UF', count({nome}) 'Pessoas'"), "valor"),
        "K2": ("Por bairro (40 maiores)", "secao"),
        "K3": (query(f"select {bairro}, {cidade}, count({nome}) where {nome} is not null "
                     f"group by {bairro}, {cidade} order by count({nome}) desc limit 40 "
                     f"label {bairro} 'Bairro', {cidade} 'Cidade', count({nome}) 'Pessoas'"), "valor"),
    }
    for i, m in enumerate(MINISTERIOS):
        r = 10 + i
        c[f"A{r}"] = (m, "rotulo")
        c[f"B{r}"] = (f'=COUNTIF({rng("Ministério")},A{r})', "valor")
    c["A18"] = ("Os números vêm da aba Inscrições, que o n8n preenche a cada inscrição no site.", "nota")
    return c


def para_ptbr(formula: str) -> str:
    """Troca a vírgula entre argumentos por ponto e vírgula (planilha em pt_BR).

    Pela API, a planilha interpreta as fórmulas no idioma dela; em pt_BR os
    argumentos são separados por ';'. Vírgulas dentro de aspas (como no texto do
    QUERY) ficam como estão.
    """
    out, aspas = [], False
    for ch in formula:
        if ch == '"':
            aspas = not aspas
        out.append(";" if ch == "," and not aspas else ch)
    return "".join(out)


def build(out: Path) -> None:
    wb = Workbook()
    head_font = Font(name=FONT, bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor=BLUE)
    estilos = {
        "titulo": (Font(name=FONT, bold=True, size=14, color=INK), None),
        "secao": (Font(name=FONT, bold=True, color=BLUE), None),
        "rotulo": (Font(name=FONT, color=INK), PatternFill("solid", fgColor=PAPER)),
        "valor": (Font(name=FONT, color=INK), None),
        "nota": (Font(name=FONT, italic=True, color="5D616C"), None),
    }

    ws = wb.active
    ws.title = "Inscrições"
    for i, (nome, largura) in enumerate(COLUNAS, start=1):
        cell = ws.cell(row=1, column=i, value=nome)
        cell.font = head_font
        cell.fill = head_fill
        cell.alignment = Alignment(vertical="center")
        ws.column_dimensions[get_column_letter(i)].width = largura
    ws.row_dimensions[1].height = 24
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{ULTIMA}1"

    rs = wb.create_sheet("Resumo")
    larguras = {"A": 30, "B": 12, "D": 12, "E": 10, "G": 26, "H": 6, "I": 10, "K": 26, "L": 22, "M": 10}
    for col, w in larguras.items():
        rs.column_dimensions[col].width = w
    for ref, (valor, estilo) in resumo_celulas().items():
        rs[ref] = valor
        font, fill = estilos[estilo]
        rs[ref].font = font
        if fill:
            rs[ref].fill = fill

    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    print(f"ok: {out}")


if __name__ == "__main__":
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("Behold-Inscricoes.xlsx"))
