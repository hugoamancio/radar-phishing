"""Medidor de risco e explicacao da nota, no mesmo visual do resto do sistema."""

from __future__ import annotations

from rich.table import Table
from rich.text import Text

from monitor.cores import COR_ALERTA, COR_ATENCAO, COR_BORDA, COR_OK, COR_ROTULO
from risco.modelo import NOMES_NIVEIS, Avaliacao

COR_NIVEL = {
    "baixo": COR_OK,
    "medio": COR_ATENCAO,
    "alto": "#E0823D",          # entre o ambar e o vermelho
    "critico": COR_ALERTA,
}


def medidor(nota: int, nivel: str, largura: int = 20, com_rotulo: bool = True) -> Text:
    """██████████████░░░░░░  72  Alto"""
    cheios = round(nota / 100 * largura)
    cor = COR_NIVEL[nivel]
    texto = Text("█" * cheios, style=cor)
    texto.append("░" * (largura - cheios), style=COR_BORDA)
    if com_rotulo:
        texto.append(f"  {nota:>2}", style=f"bold {cor}")
        texto.append(f"  {NOMES_NIVEIS[nivel]}", style=cor)
    return texto


def mini(nota: int, nivel: str) -> Text:
    """Versao curta para colunas de tabela: ▰▰▰▰▱ 82"""
    cheios = round(nota / 20)
    texto = Text("▰" * cheios, style=COR_NIVEL[nivel])
    texto.append("▱" * (5 - cheios), style=COR_BORDA)
    texto.append(f" {nota:>2}", style=f"bold {COR_NIVEL[nivel]}")
    return texto


def explicacao(a: Avaliacao) -> Table:
    """Quanto cada sinal somou, do mais forte ao mais fraco. A soma e a nota."""
    grade = Table.grid(padding=(0, 2))
    grade.add_column(no_wrap=True)
    grade.add_column(justify="right", no_wrap=True)
    grade.add_column(no_wrap=True)
    maior = max((c.pontos for c in a.contribuicoes), default=1) or 1
    sem_efeito = [c.nome for c in a.contribuicoes if c.pontos == 0]
    for c in a.contribuicoes:
        if c.pontos == 0:
            continue
        barra = Text("▪" * max(1, round(c.pontos / maior * 12)), style=COR_NIVEL[a.nivel])
        grade.add_row(Text(c.nome, style="white"), Text(f"+{c.pontos}", style="bold white"), barra)
    if sem_efeito:
        # Com a nota perto do teto, sinais extras confirmam o golpe mas ja nao somam pontos.
        n = len(sem_efeito)
        grade.add_row(Text(f"Mais {n} sina{'is' if n > 1 else 'l'}", style=COR_ROTULO), Text("+0", style=COR_ROTULO),
                      Text("confirmam o golpe, mas a nota já estava no teto", style=COR_ROTULO))
    grade.add_row(Text("Nota", style=COR_ROTULO), Text(f"{a.nota}", style=f"bold {COR_NIVEL[a.nivel]}"),
                  Text(f"de 100  ·  modelo {a.modelo}", style=COR_ROTULO))
    return grade
