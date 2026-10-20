"""Painel ao vivo do monitor no terminal (biblioteca Rich).

So desenha: o estado vem de ``Estado``, atualizado pelo laco principal.
O Rich redesenha a tela 4 vezes por segundo chamando ``Painel.__rich_console__``,
que escolhe o layout pela largura do terminal.
"""

from __future__ import annotations

import time
import unicodedata
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

from rich import box
from rich.console import Console, ConsoleOptions, Group, RenderResult
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from monitor.detector import NOMES_TECNICAS  # noqa: F401  (reexportado para quem importa daqui)
from monitor.normalizacao import decodificar_idn

from monitor.cores import (COR_ALERTA, COR_ATENCAO, COR_BORDA, COR_DESTAQUE, COR_OK,  # noqa: E402,F401
                           COR_ROTULO, COR_VALOR)
from risco.visual import mini  # noqa: E402

TECNICAS_REFORCO = ("palavra_isca", "tld_suspeito")
BARRAS = " ▁▂▃▄▅▆▇█"


@dataclass
class LinhaDeteccao:
    hora: datetime
    dominio: str
    trecho: str
    principal: str
    reforcos: list[str]
    emissor: str | None
    nota: int = 0
    nivel: str = "baixo"


@dataclass
class Estado:
    inicio: float = field(default_factory=time.monotonic)
    status: str = "iniciando"
    certificados: int = 0
    dominios: int = 0
    suspeitos_total: int = 0
    suspeitos_sessao: int = 0
    banco_ok: bool = True
    ultima_deteccao: float | None = None
    deteccoes: deque[LinhaDeteccao] = field(default_factory=lambda: deque(maxlen=14))
    por_segundo: deque[int] = field(default_factory=lambda: deque([0] * 60, maxlen=60))
    _segundo_atual: int = 0
    _contagem_segundo: int = 0

    def contar_certificado(self) -> None:
        self.certificados += 1
        agora = int(time.monotonic())
        if agora != self._segundo_atual:
            if self._segundo_atual:
                self.por_segundo.append(self._contagem_segundo)
            self._segundo_atual, self._contagem_segundo = agora, 0
        self._contagem_segundo += 1

    @property
    def ritmo(self) -> int:
        recentes = list(self.por_segundo)[-5:]
        return round(sum(recentes) / len(recentes)) if recentes else 0


def _numero(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _duracao(segundos: float) -> str:
    s = int(segundos)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def _ha_quanto(momento: float | None) -> str:
    if momento is None:
        return "nenhuma ainda"
    s = int(time.monotonic() - momento)
    if s < 60:
        return f"há {s} s"
    if s < 3600:
        return f"há {s // 60} min"
    return f"há {s // 3600} h"


def _grafico(valores: list[int], largura: int = 30) -> Text:
    # Escala entre minimo e maximo da janela: o ritmo oscila entre ~1.200 e
    # ~1.700/s, e com escala a partir de zero todas as barras ficariam iguais.
    amostra = [v for v in valores[-largura:] if v] or [0]
    menor, maior = min(amostra), max(amostra)
    faixa = (maior - menor) or 1
    barras = "".join(BARRAS[1 + round((v - menor) / faixa * (len(BARRAS) - 2))] for v in amostra)
    # "crop": num cartao estreito o grafico perde as barras mais antigas, sem "…".
    return Text(barras, style=COR_DESTAQUE, overflow="crop")


ALFABETOS = {"CYRILLIC": "cirílico", "GREEK": "grego", "ARMENIAN": "armênio", "LATIN": "latino estendido"}


def _descrever_letra(c: str) -> str:
    """'а' -> 'o "а" é a letra "a" do alfabeto cirílico'."""
    nome = unicodedata.name(c, "")
    alfabeto = ALFABETOS.get(nome.split(" ")[0], "outro alfabeto")
    letra = nome.rsplit(" ", 1)[-1].lower() if "LETTER" in nome else "?"
    return f'o "{c}" é a letra "{letra}" do alfabeto {alfabeto}'


def _dominio_destacado(dominio: str, trecho: str) -> Text:
    """Dominio com o trecho que imita a marca em vermelho."""
    visivel = decodificar_idn(dominio)
    trecho_visivel = decodificar_idn(trecho)
    texto = Text(visivel, style="white")
    pos = visivel.find(trecho_visivel)
    if pos >= 0:
        texto.stylize(COR_ALERTA, pos, pos + len(trecho_visivel))
    # Letras de outro alfabeto sao identicas na tela: sublinha e nomeia cada uma.
    estrangeiras = []
    for i, c in enumerate(visivel):
        if not c.isascii():
            texto.stylize("underline", i, i + 1)
            estrangeiras.append(_descrever_letra(c))
    if visivel != dominio:
        texto.append(f"\n{dominio}", style=COR_ROTULO)  # forma real (punycode)
    if estrangeiras:
        texto.append("\n" + "; ".join(dict.fromkeys(estrangeiras)), style=COR_ATENCAO)
    return texto


class Painel:
    def __init__(self, estado: Estado, marcas: list[str]) -> None:
        self.estado = estado
        self.marcas = marcas

    def _cabecalho(self, largura: int) -> Panel:
        e = self.estado
        if e.status == "conectado":
            status = Text("● conectado", style=COR_OK)
        else:
            status = Text(f"● {e.status}", style=COR_ATENCAO)

        esquerda = Text("Radar Phishing", style="bold white")
        if largura >= 80:
            esquerda.append("  ·  ", style=COR_BORDA)
            esquerda.append("Monitor de domínios", style=COR_DESTAQUE)
        direita = Text.assemble(status, ("   ", ""), (_duracao(time.monotonic() - e.inicio), COR_ROTULO))
        # Status e cronometro nunca somem; se faltar espaco, o titulo e que encolhe.
        grade = Table.grid(expand=True)
        grade.add_column(justify="left", no_wrap=True, overflow="ellipsis", ratio=1)
        grade.add_column(justify="right", no_wrap=True, min_width=len(direita.plain))
        grade.add_row(esquerda, direita)
        return Panel(grade, box=box.ROUNDED, border_style=COR_BORDA, padding=(0, 1))

    def _cartao(self, rotulo: str, valor: Text | str, detalhe: Text | str = "") -> Panel:
        # Cada cartao tem altura fixa (3 linhas de texto). Uma linha que
        # quebrasse empurraria a borda de baixo para fora do espaco reservado,
        # entao todo texto aqui e cortado com reticencias em vez de quebrar.
        linhas = [
            Text(rotulo, style=COR_ROTULO),
            valor if isinstance(valor, Text) else Text(valor, style=COR_VALOR),
            detalhe if isinstance(detalhe, Text) else Text(detalhe, style=COR_ROTULO),
        ]
        for t in linhas:
            t.no_wrap = True
            t.overflow = t.overflow or "ellipsis"
        return Panel(Group(*linhas), box=box.ROUNDED, border_style=COR_BORDA, padding=(0, 2))

    def _cartoes(self, colunas: int) -> Table:
        """Quatro indicadores: em linha numa tela larga, em 2x2 numa estreita."""
        e = self.estado
        grade = Table.grid(expand=True, padding=(0, 1))
        for _ in range(colunas):
            grade.add_column(ratio=1)

        sessao = f"+{e.suspeitos_sessao} nesta sessão" if e.suspeitos_sessao else "nenhum nesta sessão"
        suspeitos = Text(_numero(e.suspeitos_total), style=COR_ALERTA if e.suspeitos_sessao else COR_VALOR)
        banco = Text("gravando no PostgreSQL", style=COR_ROTULO) if e.banco_ok \
            else Text("banco indisponível: só na tela", style=COR_ATENCAO)

        cartoes = [
            self._cartao("Certificados analisados", _numero(e.certificados),
                         f"{_numero(e.dominios)} domínios"),
            self._cartao("Ritmo", Text.assemble((_numero(e.ritmo), COR_VALOR), (" por segundo", COR_ROTULO)),
                         _grafico(list(e.por_segundo))),
            self._cartao("Domínios suspeitos", suspeitos, sessao),
            self._cartao("Última detecção", _ha_quanto(e.ultima_deteccao), banco),
        ]
        for i in range(0, 4, colunas):
            grade.add_row(*cartoes[i:i + colunas])
        return grade

    def _tabela(self, largo: bool, compacto: bool = False) -> Panel:
        """Detecções recentes. Numa tela estreita, emissor sai e os reforços vão para baixo da técnica."""
        # leading=1 deixa uma linha em branco entre deteccoes: um dominio com
        # punycode ocupa 3 linhas e, sem respiro, se mistura com o vizinho.
        tabela = Table(box=box.SIMPLE_HEAD, expand=True, show_edge=False, leading=1,
                       header_style=COR_ROTULO, border_style=COR_BORDA, pad_edge=False)
        tabela.add_column("Hora", width=8, style=COR_ROTULO, no_wrap=True)
        if largo:
            tabela.add_column("Risco", width=8, no_wrap=True)
        tabela.add_column("Domínio", ratio=4, overflow="fold")
        if largo:
            # Largura fixa do maior nome: com colunas proporcionais, "Marca só no
            # subdomínio" virava "Marca só no sub…" num terminal de 120 colunas.
            tabela.add_column("Técnica", width=22, no_wrap=True)
            tabela.add_column("Reforços", width=12, style=COR_ATENCAO, no_wrap=True)
            tabela.add_column("Emissor", width=14, style=COR_ROTULO, overflow="ellipsis", no_wrap=True)  # "Let's Encrypt"
        elif not compacto:
            tabela.add_column("Técnica", width=22, no_wrap=True)  # cabe "Marca só no subdomínio"

        for d in self.estado.deteccoes:
            tecnica = Text(NOMES_TECNICAS.get(d.principal, d.principal), style="white")
            reforcos = [NOMES_TECNICAS[r] for r in d.reforcos]
            hora = d.hora.strftime("%H:%M:%S")
            dominio = _dominio_destacado(d.dominio, d.trecho)
            if largo:
                # Um reforco por linha: nunca quebra "TLD suspeito" no meio.
                tabela.add_row(hora, mini(d.nota, d.nivel), dominio, tecnica,
                               "\n".join(reforcos) or Text("—", style=COR_BORDA), d.emissor or "—")
            elif not compacto:
                # Sem coluna propria de risco: a nota vai na primeira linha da tecnica.
                celula = mini(d.nota, d.nivel)
                celula.append("\n")
                celula.append_text(tecnica)
                for r in reforcos:
                    celula.append(f"\n+ {r}", style=COR_ATENCAO)
                tabela.add_row(hora, dominio, celula)
            else:
                # Terminal muito estreito: tudo empilhado, para o dominio nao quebrar no meio.
                celula = mini(d.nota, d.nivel)
                celula.append("  ")
                celula.append_text(tecnica)
                celula.append("\n")
                celula.append_text(dominio)
                if reforcos:
                    celula.append("\n+ " + ", ".join(reforcos), style=COR_ATENCAO)
                tabela.add_row(hora, celula)

        if not self.estado.deteccoes:
            vazio = Text("\nNenhum domínio suspeito ainda.\n"
                         "Golpes aparecem em rajadas: deixe o monitor rodando.\n", style=COR_ROTULO, justify="center")
            return Panel(vazio, title="Detecções recentes", title_align="left",
                         box=box.ROUNDED, border_style=COR_BORDA)

        return Panel(tabela, title="Detecções recentes", title_align="left",
                     box=box.ROUNDED, border_style=COR_BORDA, padding=(0, 1))

    def _rodape(self) -> Text:
        return Text.assemble(
            ("Marcas monitoradas: ", COR_ROTULO), (", ".join(self.marcas), "white"),
            ("    Ctrl+C para sair", COR_BORDA),
        )

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        # Abaixo de 110 colunas os quatro cartoes nao cabem lado a lado sem
        # cortar texto ("Certifi..."), entao passam para uma grade 2x2.
        largura = options.max_width
        colunas = 4 if largura >= 110 else 2
        layout = Layout()
        layout.split_column(
            Layout(self._cabecalho(largura), name="cabecalho", size=3),
            Layout(self._cartoes(colunas), name="cartoes", size=5 * (4 // colunas)),
            Layout(self._tabela(largo=largura >= 110, compacto=largura < 75), name="tabela"),
            Layout(self._rodape(), name="rodape", size=1),
        )
        yield layout
