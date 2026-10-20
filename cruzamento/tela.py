"""Tela do cruzamento: indicadores no topo e uma linha do tempo por golpe."""

from __future__ import annotations

from rich import box
from rich.console import Console, ConsoleOptions, Group, RenderResult
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from cruzamento.consulta import Cruzamento, Resumo, duracao
from monitor.cores import COR_ATENCAO, COR_BORDA, COR_DESTAQUE, COR_OK, COR_ROTULO, COR_VALOR
from risco.visual import mini

NOMES_CANAIS = {"e-mail": "E-mail", "sms": "SMS", "whatsapp": "WhatsApp", "outro": "Mensagem"}


def _cartao(rotulo: str, valor: Text | str, detalhe: str = "") -> Panel:
    linhas = [Text(rotulo, style=COR_ROTULO),
              valor if isinstance(valor, Text) else Text(valor, style=COR_VALOR),
              Text(detalhe, style=COR_ROTULO)]
    for t in linhas:
        t.no_wrap, t.overflow = True, "ellipsis"
    return Panel(Group(*linhas), box=box.ROUNDED, border_style=COR_BORDA, padding=(0, 2))


def _data(momento) -> str:
    return momento.astimezone().strftime("%d/%m %H:%M") if momento else "—"


def linha_do_tempo(c: Cruzamento) -> Text:
    """CT 16/10 09:12 ──── 3 d 2 h antes ───▶ e-mail 19/10 11:40"""
    canal = NOMES_CANAIS.get(c.canal, c.canal)
    t = Text()
    if c.situacao == "antes":
        t.append("● ", style=COR_DESTAQUE)
        t.append(f"CT logs {_data(c.visto_nos_ct_em)}", style="white")
        t.append("  ──  ", style=COR_BORDA)
        t.append(f"{duracao(c.antecedencia)} antes", style=f"bold {COR_OK}")
        t.append("  ──▶  ", style=COR_BORDA)
        t.append(f"{canal} {_data(c.chegou_em)}", style="white")
    elif c.situacao == "depois":
        t.append("● ", style=COR_ATENCAO)
        t.append(f"{canal} {_data(c.chegou_em)}", style="white")
        t.append("  ──  ", style=COR_BORDA)
        t.append(f"{duracao(c.antecedencia)} depois", style=f"bold {COR_ATENCAO}")
        t.append("  ──▶  ", style=COR_BORDA)
        t.append(f"CT logs {_data(c.visto_nos_ct_em)}", style="white")
    else:
        t.append("● ", style=COR_BORDA)
        t.append(f"{canal} {_data(c.chegou_em)}", style="white")
        t.append("   nunca visto nos CT logs", style=COR_ROTULO)
    return t


class TelaCruzamento:
    def __init__(self, itens: list[Cruzamento], resumo: Resumo) -> None:
        self.itens, self.resumo = itens, resumo

    def _cartoes(self, colunas: int) -> Table:
        r = self.resumo
        taxa = f"{r.taxa_antecipada:.0%} já conhecidos" if r.total else "nenhum ainda"
        cartoes = [
            _cartao("Golpes que chegaram", str(r.total), "por e-mail, SMS ou WhatsApp"),
            _cartao("Conhecidos antes", Text(str(r.antes), style=f"bold {COR_OK}" if r.antes else COR_VALOR), taxa),
            _cartao("Antecedência mediana", duracao(r.mediana), f"maior: {duracao(r.maior)}"),
            _cartao("Vistos só depois", str(r.depois),
                    f"{r.desconhecidos} nunca visto{'' if r.desconhecidos == 1 else 's'} nos CT logs"),
        ]
        grade = Table.grid(expand=True, padding=(0, 1))
        for _ in range(colunas):
            grade.add_column(ratio=1)
        for i in range(0, 4, colunas):
            grade.add_row(*cartoes[i:i + colunas])
        return grade

    def _tabela(self, largo: bool) -> Panel:
        if not self.itens:
            vazio = Text("\nNenhum golpe chegou por e-mail ou mensagem ainda.\n"
                         "Analise e-mails (python -m analisador) e mensagens (python -m mensagem):\n"
                         "cada link suspeito é comparado com o que o monitor já viu nos CT logs.\n",
                         style=COR_ROTULO, justify="center")
            return Panel(vazio, title="Linha do tempo", title_align="left", box=box.ROUNDED, border_style=COR_BORDA)
        tabela = Table(box=box.SIMPLE_HEAD, expand=True, show_edge=False, leading=1, pad_edge=False,
                       header_style=COR_ROTULO, border_style=COR_BORDA)
        if largo:
            tabela.add_column("Risco", width=8, no_wrap=True)
            tabela.add_column("Domínio", ratio=2, overflow="fold")
            tabela.add_column("Linha do tempo", ratio=3, overflow="fold")
            for c in self.itens:
                risco = mini(c.nota, c.nivel) if c.nota is not None else Text("—", style=COR_BORDA)
                tabela.add_row(risco, Text(c.dominio, style="white"), linha_do_tempo(c))
        else:
            tabela.add_column("Golpe", ratio=1, overflow="fold")
            for c in self.itens:
                celula = mini(c.nota, c.nivel) if c.nota is not None else Text("—", style=COR_BORDA)
                celula.append(f"  {c.dominio}\n", style="white")
                celula.append_text(linha_do_tempo(c))
                tabela.add_row(celula)
        return Panel(tabela, title="Linha do tempo", title_align="left", box=box.ROUNDED,
                     border_style=COR_BORDA, padding=(0, 1))

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        largura = options.max_width
        titulo = Text.assemble(("Radar Phishing", "bold white"), ("  ·  ", COR_BORDA),
                               ("Cruzamento: CT logs × e-mails e mensagens", COR_DESTAQUE))
        yield Panel(titulo, box=box.ROUNDED, border_style=COR_BORDA, padding=(0, 1))
        yield self._cartoes(4 if largura >= 110 else 2)
        yield self._tabela(largo=largura >= 110)
        yield Text("Antecedência = tempo entre o certificado aparecer nos CT logs e o link chegar até a pessoa.",
                   style=COR_ROTULO)
