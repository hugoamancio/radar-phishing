"""Agrupa deteccoes em campanhas: o mesmo golpista atras de dominios diferentes.

Caso real (19/10/2026) que motivou o agrupamento:

    fcxwpuwj.bradesco.support.bloodoperationbag.xyz
    gsvgecou.bradesco.support.yearbladeoven.click

O prefixo (8 letras aleatorias) muda a cada host e o dominio registrado muda a
cada dia, mas o "molde" no meio, bradesco.support, fica. Molde = os rotulos do
subdominio a partir do que cita a marca, sem os "www". Deteccoes com o mesmo
molde viram uma campanha; sem molde (a marca esta no proprio dominio
registrado, ex.: bradesco-cancelar.top), o agrupamento e pelo dominio registrado.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from monitor.normalizacao import dominio_organizacional


@dataclass
class Deteccao:
    dominio: str
    nota: int
    nivel: str
    tecnicas: list[str]
    emissor: str | None
    quando: datetime


@dataclass
class Campanha:
    chave: str                    # o molde (bradesco.support) ou o dominio registrado
    por_molde: bool
    deteccoes: list[Deteccao] = field(default_factory=list)

    @property
    def hosts(self) -> list[str]:
        return sorted({d.dominio for d in self.deteccoes})

    @property
    def enderecos(self) -> list[str]:
        """Hosts sem o "www.": site.com e www.site.com sao o mesmo endereco, nao uma campanha."""
        return sorted({h.removeprefix("www.") for h in self.hosts})

    @property
    def e_campanha(self) -> bool:
        return len(self.enderecos) > 1

    @property
    def dominios_registrados(self) -> list[str]:
        return sorted({dominio_organizacional(d.dominio) for d in self.deteccoes})

    @property
    def tlds(self) -> Counter:
        return Counter(r.rsplit(".", 1)[-1] for r in self.dominios_registrados)

    @property
    def emissores(self) -> Counter:
        return Counter(d.emissor or "desconhecido" for d in self.deteccoes)

    @property
    def nota_maxima(self) -> int:
        return max(d.nota for d in self.deteccoes)

    @property
    def primeira(self) -> datetime:
        return min(d.quando for d in self.deteccoes)

    @property
    def ultima(self) -> datetime:
        return max(d.quando for d in self.deteccoes)


def molde(dominio: str, palavras_marca: tuple[str, ...]) -> str | None:
    rotulos = dominio.lower().split(".")
    tamanho_org = len(dominio_organizacional(dominio).split("."))
    sub = rotulos[:len(rotulos) - tamanho_org]
    inicio = next((i for i, r in enumerate(sub) if any(p in r for p in palavras_marca)), None)
    if inicio is None:
        return None
    resto: list[str] = []
    for r in sub[inicio:]:
        if r != "www" and (not resto or resto[-1] != r):
            resto.append(r)
    return ".".join(resto) or None


def agrupar(deteccoes: list[Deteccao], palavras_marca: tuple[str, ...]) -> list[Campanha]:
    grupos: dict[tuple[bool, str], Campanha] = {}
    for d in deteccoes:
        m = molde(d.dominio, palavras_marca)
        chave = (True, m) if m else (False, dominio_organizacional(d.dominio))
        grupos.setdefault(chave, Campanha(chave[1], chave[0])).deteccoes.append(d)
    # Mais hosts primeiro; empate, a mais grave.
    return sorted(grupos.values(), key=lambda c: (-len(c.enderecos), -c.nota_maxima, c.chave))
