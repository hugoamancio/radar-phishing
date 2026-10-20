"""Analisa SMS e mensagens de WhatsApp.

    python -m mensagem                                   caixa para colar a mensagem
    python -m mensagem "texto da mensagem" --de 27888    direto
    python -m mensagem "texto" --canal whatsapp --nao-gravar

Analise so mensagens suas ou que alguem autorizou. O texto nunca e gravado.
"""

from __future__ import annotations

import argparse

from rich.console import Console
from rich.text import Text

from mensagem.analise import CANAIS, analisar
from mensagem.banco import gravar
from mensagem.tela import relatorio
from monitor.__main__ import _marcas_e_conexao
from monitor.cores import COR_BORDA, COR_DESTAQUE, COR_ROTULO

console = Console()


def _ler_colado() -> tuple[str, str, str | None] | None:
    console.print(Text.assemble(("Radar Phishing", "bold white"), ("  ·  ", COR_BORDA),
                                ("SMS e WhatsApp", COR_DESTAQUE)))
    console.print(Text("Cole a mensagem e aperte Enter numa linha vazia para analisar. "
                       "Enter vazio logo de cara para sair.\n", style=COR_ROTULO))
    linhas: list[str] = []
    while True:
        try:
            linha = input()
        except (EOFError, KeyboardInterrupt):
            break
        if not linha.strip():
            break
        linhas.append(linha)
    if not linhas:
        return None
    canal = console.input(Text("Canal [sms/whatsapp] (Enter = sms) › ", style=COR_DESTAQUE)).strip().lower() or "sms"
    if canal not in CANAIS:
        canal = "outro"
    de = console.input(Text("Quem enviou? número ou nome (Enter = pular) › ", style=COR_DESTAQUE)).strip() or None
    return "\n".join(linhas), canal, de


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m mensagem", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("texto", nargs="?", help="a mensagem; sem ele, abre a caixa para colar")
    parser.add_argument("--canal", choices=CANAIS, default="sms")
    parser.add_argument("--de", help="número ou nome de quem enviou")
    parser.add_argument("--nao-gravar", action="store_true", help="só mostra, não grava no banco")
    args = parser.parse_args()

    marcas, conn = _marcas_e_conexao()
    entradas = [(args.texto, args.canal, args.de)] if args.texto else []
    while True:
        if not entradas:
            colado = _ler_colado()
            if colado is None:
                return
            entradas.append(colado)
        texto, canal, de = entradas.pop()
        a = analisar(texto, marcas, canal, de, conn=conn)
        gravado = None
        if not args.nao_gravar:
            try:
                gravar(conn, a, marcas) if conn else None
                gravado = conn is not None
            except Exception:
                gravado = False
        console.print(relatorio(a, gravado))
        console.print()
        if args.texto:
            return


if __name__ == "__main__":
    main()
