"""Le o cruzamento do banco e resume em numeros.

A pergunta que estes numeros respondem: dos golpes que chegaram por e-mail,
SMS ou WhatsApp, quantos o monitor ja conhecia, e com quanta antecedencia?
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class Cruzamento:
    dominio: str
    canal: str
    origem_id: int
    de: str | None
    chegou_em: datetime
    visto_nos_ct_em: datetime | None
    certificados: int | None
    antecedencia: timedelta | None
    situacao: str               # antes, depois, desconhecido
    nota: int | None
    nivel: str | None


@dataclass
class Resumo:
    total: int
    antes: int
    depois: int
    desconhecidos: int
    mediana: timedelta | None
    maior: timedelta | None

    @property
    def taxa_antecipada(self) -> float | None:
        return self.antes / self.total if self.total else None


def ler(conn, limite: int = 200) -> list[Cruzamento]:
    linhas = conn.execute(
        "SELECT dominio, canal, origem_id, de, chegou_em, visto_nos_ct_em, certificados, antecedencia, "
        "situacao, nota, nivel FROM vw_cruzamento LIMIT %s", (limite,)).fetchall()
    return [Cruzamento(*l) for l in linhas]


def resumir(itens: list[Cruzamento]) -> Resumo:
    antes = [c.antecedencia for c in itens if c.situacao == "antes"]
    return Resumo(
        total=len(itens),
        antes=len(antes),
        depois=sum(c.situacao == "depois" for c in itens),
        desconhecidos=sum(c.situacao == "desconhecido" for c in itens),
        mediana=statistics.median(antes) if antes else None,
        maior=max(antes) if antes else None,
    )


def duracao(t: timedelta | None) -> str:
    """3 d 4 h, 5 h 20 min, 12 min."""
    if t is None:
        return "—"
    segundos = int(abs(t.total_seconds()))
    d, resto = divmod(segundos, 86400)
    h, resto = divmod(resto, 3600)
    m = resto // 60
    if d:
        return f"{d} d {h} h" if h else f"{d} d"
    if h:
        return f"{h} h {m} min" if m else f"{h} h"
    return f"{m} min"
