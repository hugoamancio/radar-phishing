"""Ponto de entrada do monitor de dominios.

    python -m monitor                      painel ao vivo, lendo os CT logs
    python -m monitor testar DOMINIO...    explica o veredito para dominios avulsos
    python -m monitor pesquisar [URL...]   procura o endereco no banco de golpes
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import datetime, timezone

from rich import box
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from monitor import banco
from monitor.detector import Marca, analisar
from monitor.painel import (COR_ALERTA, COR_BORDA, COR_OK, COR_ROTULO, NOMES_TECNICAS,
                            TECNICAS_REFORCO, Estado, LinhaDeteccao, Painel, _dominio_destacado)
from monitor.fonte_ct import certificados
from monitor.painel import COR_DESTAQUE
from monitor.pesquisa import pesquisar
from monitor.tela_pesquisa import cartao
from risco.modelo import calcular

console = Console()


def _marcas_e_conexao():
    """Conecta no banco; se ele estiver fora, segue com o Bradesco embutido."""
    try:
        conn = banco.conectar()
        return banco.carregar_marcas(conn), conn
    except Exception:
        reserva = Marca(1, "Bradesco",
                        ("bradesco.com.br", "bradesco", "bradescoseguros.com.br", "next.me"),
                        ("bradesco", "bradesc0", "bradescco", "bradesko", "bradesconet"), "237")
        return [reserva], None


def _carregar_recentes(conn, estado: Estado) -> None:
    linhas = conn.execute(
        "SELECT dominio, trecho, tecnicas, emissor, detectado_em "
        "FROM vw_dominios_suspeitos LIMIT %s", (estado.deteccoes.maxlen,)
    ).fetchall()
    for dominio, trecho, tecnicas, emissor, quando in reversed(linhas):
        principal = next((t for t in tecnicas if t not in TECNICAS_REFORCO), tecnicas[0])
        risco = calcular(tecnicas)   # modelo atual, mesmo para deteccoes antigas
        estado.deteccoes.appendleft(LinhaDeteccao(
            quando.astimezone(), dominio, trecho, principal,
            [t for t in tecnicas if t in TECNICAS_REFORCO], emissor, risco.nota, risco.nivel))
    estado.suspeitos_total = banco.contar_suspeitos(conn)


async def monitorar() -> None:
    marcas, conn = _marcas_e_conexao()
    estado = Estado(banco_ok=conn is not None)
    if conn:
        _carregar_recentes(conn, estado)
    painel = Painel(estado, [m.nome for m in marcas])

    def mudar_status(s: str) -> None:
        estado.status = s

    vistos: set[tuple[str, int]] = set()   # (dominio, marca) ja exibidos nesta sessao
    inicio = datetime.now(timezone.utc)
    ultimo_batimento = 0.0

    with Live(painel, console=console, refresh_per_second=4, screen=True):
        async for cert in certificados(mudar_status):
            estado.contar_certificado()
            # Batimento a cada 10 s: e por ele que o dashboard sabe que o monitor esta vivo.
            # So bate enquanto chegam certificados; se o fluxo travar, o dashboard mostra "parado".
            if conn and time.monotonic() - ultimo_batimento >= 10:
                ultimo_batimento = time.monotonic()
                try:
                    banco.bater(conn, estado.certificados, estado.ritmo, inicio)
                except Exception:
                    estado.banco_ok = False
            for nome in cert["dominios"]:
                estado.dominios += 1
                for det in analisar(nome, marcas):
                    chave = (det.dominio, det.marca.id)
                    if chave in vistos:
                        continue
                    vistos.add(chave)

                    novo = True
                    if conn:
                        try:
                            novo = banco.gravar(conn, det, cert)
                        except Exception:
                            estado.banco_ok = False
                    if novo:
                        estado.suspeitos_total += 1
                        estado.suspeitos_sessao += 1
                    estado.ultima_deteccao = time.monotonic()
                    risco = calcular(det.tecnicas)
                    estado.deteccoes.appendleft(LinhaDeteccao(
                        datetime.now(), det.dominio, det.trecho, det.principal,
                        [t for t in det.tecnicas if t in TECNICAS_REFORCO], cert["emissor"],
                        risco.nota, risco.nivel))


def testar(dominios: list[str]) -> None:
    marcas, _ = _marcas_e_conexao()
    for nome in dominios:
        resultado = analisar(nome, marcas)
        if not resultado:
            console.print(Panel(Text.assemble((nome, "white"), ("\nNenhum sinal de imitação.", COR_OK)),
                                box=box.ROUNDED, border_style=COR_BORDA, title="Sem suspeita",
                                title_align="left", padding=(0, 2)))
            continue
        for det in resultado:
            motivos = Table.grid(padding=(0, 2))
            motivos.add_column(style="white", no_wrap=True)
            motivos.add_column(style=COR_ROTULO)
            for m in det.motivos:
                motivos.add_row(NOMES_TECNICAS[m["tecnica"]], m["detalhe"])
            corpo = Table.grid()
            corpo.add_row(_dominio_destacado(det.dominio, det.trecho))
            corpo.add_row(Text(f"\nImita: {det.marca.nome}\n", style=COR_ROTULO))
            corpo.add_row(motivos)
            console.print(Panel(corpo, box=box.ROUNDED, border_style=COR_ALERTA,
                                title=f"Suspeito  ·  {NOMES_TECNICAS[det.principal]}",
                                title_align="left", padding=(0, 2)))


def pesquisar_enderecos(enderecos: list[str]) -> None:
    """Pesquisa os endereços dados; sem nenhum, abre uma caixa de pesquisa no terminal."""
    marcas, conn = _marcas_e_conexao()
    if enderecos:
        for e in enderecos:
            console.print(cartao(pesquisar(e, marcas, conn)))
        return

    console.print(Text.assemble(("Radar Phishing", "bold white"), ("  ·  ", COR_BORDA),
                                ("Pesquisa de endereço", COR_DESTAQUE)))
    console.print(Text("Cole a URL ou o domínio suspeito. O endereço nunca é acessado. "
                       "Enter vazio para sair.\n", style=COR_ROTULO))
    while True:
        try:
            entrada = console.input(Text("Endereço › ", style=COR_DESTAQUE)).strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not entrada:
            break
        console.print(cartao(pesquisar(entrada, marcas, conn)))
        console.print()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m monitor", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="comando")
    p_testar = sub.add_parser("testar", help="analisa domínios avulsos e explica o veredito")
    p_testar.add_argument("dominios", nargs="+")
    p_pesq = sub.add_parser("pesquisar", help="procura uma URL ou domínio no banco de golpes")
    p_pesq.add_argument("enderecos", nargs="*", help="vazio abre a caixa de pesquisa")
    args = parser.parse_args()

    if args.comando == "testar":
        testar(args.dominios)
        return
    if args.comando == "pesquisar":
        pesquisar_enderecos(args.enderecos)
        return
    try:
        asyncio.run(monitorar())
    except KeyboardInterrupt:
        console.print(Text("Monitor encerrado.", style=COR_ROTULO))
        sys.exit(0)


if __name__ == "__main__":
    main()
