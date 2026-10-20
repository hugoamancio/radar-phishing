"""Cartao de resultado da pesquisa, no mesmo visual do painel do monitor."""

from __future__ import annotations

from datetime import datetime, timezone

from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from monitor.painel import (COR_ALERTA, COR_ATENCAO, COR_BORDA, COR_OK, COR_ROTULO,
                            NOMES_TECNICAS, _dominio_destacado)
from risco.visual import medidor
from monitor.pesquisa import CONHECIDO, CONHECIDO_PAI, NADA, OFICIAL, SUSPEITO_AGORA, Resultado

CONSELHO = ("Não acesse o endereço e não informe nenhum dado. Se já informou, ligue para o banco "
            "pelo número que está no verso do cartão.")


def _data(momento: datetime | None) -> str:
    if momento is None:
        return "—"
    local = momento.astimezone()
    segundos = (datetime.now(timezone.utc) - momento).total_seconds()
    if segundos < 3600:
        ha = f"há {max(1, int(segundos // 60))} min"
    elif segundos < 86400:
        ha = f"há {int(segundos // 3600)} h"
    else:
        dias = int(segundos // 86400)
        ha = f"há {dias} dia" + ("s" if dias > 1 else "")
    return f"{local:%d/%m/%Y %H:%M}  ({ha})"


def _vezes(n: int, singular: str, plural: str) -> str:
    if not n:
        return f"ainda não apareceu nas {plural}"
    return f"apareceu em {n} {singular if n == 1 else plural}"


def _fatos(linhas: list[tuple[str, str | Text]]) -> Table:
    grade = Table.grid(padding=(0, 3))
    grade.add_column(style=COR_ROTULO, no_wrap=True)
    grade.add_column(style="white")
    for rotulo, valor in linhas:
        grade.add_row(rotulo, valor)
    return grade


def _motivos(motivos: list[dict]) -> Table:
    grade = Table.grid(padding=(0, 3))
    grade.add_column(style="white", no_wrap=True)
    grade.add_column(style=COR_ROTULO)
    for m in motivos:
        grade.add_row(NOMES_TECNICAS.get(m["tecnica"], m["tecnica"]), m["detalhe"])
    return grade


def _cabeca(r: Resultado, destaque: str) -> list:
    partes: list = []
    if r.entrada.strip() != r.dominio:
        partes.append(Text(f"Você pesquisou: {r.entrada.strip()}", style=COR_ROTULO, overflow="fold"))
    dominio = _dominio_destacado(r.dominio, destaque)
    dominio.stylize("bold")
    partes += [dominio, Text("")]
    return partes


def cartao(r: Resultado) -> Panel:
    if r.dominio is None:
        corpo = Text.assemble(("Não reconheci um endereço em: ", COR_ROTULO), (r.entrada, "white"),
                              ("\nExemplos aceitos: https://site.com/login, site.com, hxxps://site[.]com",
                               COR_ROTULO))
        return Panel(corpo, title="Endereço inválido", title_align="left",
                     box=box.ROUNDED, border_style=COR_BORDA, padding=(1, 2))

    if r.tipo in (CONHECIDO, CONHECIDO_PAI):
        reg = r.registro
        if r.tipo == CONHECIDO:
            veredito = f"Este endereço já está no banco como golpe contra o {reg.marca}."
            destaque = reg.trecho
        else:
            veredito = (f"O domínio principal {reg.dominio} já está no banco como golpe contra o "
                        f"{reg.marca}. O endereço pesquisado é um subdomínio dele.")
            destaque = reg.dominio
        certs = f"{reg.certificados}"
        if reg.ultimo_emissor:
            certs += f"  ·  último emitido por {reg.ultimo_emissor}"
        emails = (f"apareceu em {reg.emails} e-mail" + ("s" if reg.emails > 1 else "") + " analisado"
                  + ("s" if reg.emails > 1 else "")) if reg.emails else "ainda não apareceu nos e-mails analisados"
        risco = r.risco
        corpo = Group(
            *_cabeca(r, destaque),
            medidor(risco.nota, risco.nivel, largura=30),
            Text(""),
            Text(veredito, style=COR_ALERTA),
            Text(""),
            _fatos([("No banco desde", _data(reg.detectado_em)),
                    ("Imita", reg.marca),
                    ("Certificados vistos", certs),
                    ("E-mails", emails),
                    ("SMS e WhatsApp", _vezes(reg.mensagens, "mensagem analisada", "mensagens analisadas"))]),
            Text(""),
            Text("Por que é golpe", style=COR_ROTULO),
            _motivos(reg.motivos),
            Text(""),
            Text(CONSELHO, style=COR_ATENCAO),
        )
        titulo = "Golpe conhecido" if r.tipo == CONHECIDO else "Subdomínio de golpe conhecido"
        return Panel(corpo, title=titulo, title_align="left", box=box.ROUNDED,
                     border_style=COR_ALERTA, padding=(1, 2))

    if r.tipo == SUSPEITO_AGORA:
        det = r.deteccoes[0]
        aviso_banco = [] if r.banco_ok else [Text("Banco indisponível: análise feita só pelo detector.",
                                                  style=COR_ROTULO), Text("")]
        risco = r.risco
        corpo = Group(
            *_cabeca(r, det.trecho),
            medidor(risco.nota, risco.nivel, largura=30),
            Text(""),
            Text(f"Ainda não está no banco, mas imita o {det.marca.nome}.", style=COR_ATENCAO + " bold"),
            Text(""),
            *aviso_banco,
            Text("Por que parece golpe", style=COR_ROTULO),
            _motivos(det.motivos),
            Text(""),
            Text(CONSELHO, style=COR_ATENCAO),
        )
        return Panel(corpo, title="Parece golpe", title_align="left", box=box.ROUNDED,
                     border_style=COR_ATENCAO, padding=(1, 2))

    if r.tipo == OFICIAL:
        corpo = Group(
            *_cabeca(r, ""),
            Text(f"Domínio oficial do {r.marca_oficial}.", style=COR_OK + " bold"),
            Text(""),
            Text("Confira se o endereço está exatamente assim: um único caractere diferente já é "
                 "outro site.", style=COR_ROTULO),
        )
        return Panel(corpo, title="Site oficial", title_align="left", box=box.ROUNDED,
                     border_style=COR_OK, padding=(1, 2))

    assert r.tipo == NADA
    aviso = ("Não está no banco e não imita nenhuma marca monitorada. Isso não garante que o site "
             "seja seguro: o sistema só reconhece golpes contra as marcas cadastradas.")
    if not r.banco_ok:
        aviso = "Banco indisponível. " + aviso
    corpo = Group(*_cabeca(r, ""), Text("Nada encontrado.", style="bold white"), Text(""),
                  Text(aviso, style=COR_ROTULO))
    return Panel(corpo, title="Sem registro", title_align="left", box=box.ROUNDED,
                 border_style=COR_BORDA, padding=(1, 2))
