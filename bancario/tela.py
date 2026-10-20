"""Mostra o que foi lido de boletos, Pix e QR Codes, destacando o que nao bate."""

from __future__ import annotations

from rich.console import Group
from rich.table import Table
from rich.text import Text

from bancario.analise import ResultadoBancario, _real
from bancario.boleto import Boleto
from bancario.pix import Pix
from monitor.cores import COR_ALERTA, COR_BORDA, COR_OK, COR_ROTULO
from monitor.pesquisa import extrair_dominio

SELO_OK = ("confere", "bold #0d1117 on #57AB5A")
SELO_FALHA = ("não confere", "bold white on #B62324")


def _selo(ok: bool) -> Text:
    # Cor como trecho, nao como estilo do Text inteiro: senao o fundo verde se
    # estende pela coluna toda e o selo vira uma barra.
    rotulo, estilo = SELO_OK if ok else SELO_FALHA
    selo = Text()
    selo.append(f" {rotulo} ", style=estilo)
    return selo


def _fatos(linhas: list[tuple[str, Text | str]]) -> Table:
    grade = Table.grid(padding=(0, 3))
    grade.add_column(style=COR_ROTULO, no_wrap=True)
    grade.add_column(overflow="fold")
    for rotulo, valor in linhas:
        grade.add_row(rotulo, valor if isinstance(valor, Text) else Text(valor, style="white"))
    return grade


def bloco_boleto(b: Boleto, onde: str, codigo_esperado: str | None = None,
                 valores_citados: set[float] | None = None) -> Group:
    banco = Text(f"{b.banco_codigo} · {b.banco_nome or 'banco desconhecido'}" if b.banco_codigo else "—")
    divergente = bool(codigo_esperado and b.tipo == "bancario" and b.banco_codigo != codigo_esperado)
    banco.stylize(COR_ALERTA if divergente else "white")
    if divergente:
        banco.append(f"   esperado {codigo_esperado}", style=COR_ROTULO)
    conferencia = _selo(b.valido)
    for p in b.problemas:
        conferencia.append(f"\n{p}", style=COR_ALERTA)
    linhas = [("Linha", Text(b.formatada, style="white")),
              ("Tipo", "boleto bancário" if b.tipo == "bancario" else "conta de consumo ou tributo")]
    if b.tipo == "bancario":
        linhas.append(("Banco", banco))
    if b.valor is not None:
        valor = Text(_real(b.valor) if b.valor else "não informado no boleto", style="white")
        if b.valor and valores_citados and not any(abs(b.valor - v) < 0.005 for v in valores_citados):
            valor.stylize(COR_ALERTA)
            valor.append("   o texto fala em " + ", ".join(_real(v) for v in sorted(valores_citados)), style=COR_ROTULO)
        linhas.append(("Valor", valor))
    if b.vencimento:
        linhas.append(("Vencimento", f"{b.vencimento:%d/%m/%Y}"))
    linhas.append(("Conferência", conferencia))
    return Group(Text(f"Boleto  ·  {onde}", style="bold white"), _fatos(linhas))


def bloco_pix(p: Pix, onde: str, divergente: bool) -> Group:
    recebedor = Text(p.recebedor or "não informado", style=COR_ALERTA if divergente else "white")
    linhas = [("Recebedor", recebedor)]
    if p.chave:
        linhas.append(("Chave", f"{p.tipo_chave} · {p.chave}"))
    if p.url:
        linhas.append(("Pix dinâmico", f"dados buscados em {extrair_dominio(p.url) or p.url}"))
    if p.valor is not None:
        linhas.append(("Valor", _real(p.valor)))
    if p.cidade:
        linhas.append(("Cidade", p.cidade))
    conferencia = _selo(p.crc_ok)
    for problema in p.problemas:
        conferencia.append(f"\n{problema}", style=COR_ALERTA)
    linhas.append(("Conferência", conferencia))
    return Group(Text(f"Pix  ·  {onde}", style="bold white"), _fatos(linhas))


def secao(r: ResultadoBancario, links_suspeitos: set[str] | None = None) -> Group | None:
    """Blocos de boleto, Pix e QR Code. None se nao houver nenhum."""
    if r.vazio:
        return None
    blocos: list = []
    codigo = r.marca_alegada.codigo_banco if r.marca_alegada else None
    for b, onde in r.boletos:
        blocos += [bloco_boleto(b, onde, codigo, r.valores_citados), Text("")]
    divergentes = {a.detalhe.split(":")[0] for a in r.achados if a.tecnica == "pix_recebedor_divergente"}
    for p, onde in r.pix:
        blocos += [bloco_pix(p, onde, onde in divergentes), Text("")]
    qr = [(u, o) for u, o in r.qr_links if not o.startswith("Pix dinâmico")]
    if qr:
        grade = Table.grid(padding=(0, 2))
        grade.add_column(style=COR_ROTULO, no_wrap=True)
        grade.add_column(width=1)
        grade.add_column(overflow="fold")
        for url, onde in qr:
            dominio = extrair_dominio(url) or url
            perigoso = links_suspeitos is None or dominio in links_suspeitos
            grade.add_row(onde, Text("→", style=COR_BORDA), Text(dominio, style=COR_ALERTA if perigoso else COR_OK))
        blocos += [Text("QR Codes com link", style="bold white"), grade, Text("")]
    if r.marca_alegada:
        blocos.append(Text(f"A mensagem diz ser do {r.marca_alegada.nome}"
                           + (f" (código {codigo})" if codigo else "") + ".", style=COR_ROTULO))
    return Group(*blocos)
