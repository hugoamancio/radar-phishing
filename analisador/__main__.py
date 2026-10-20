"""Analisa e-mails salvos como .eml (proprios ou autorizados).

    python -m analisador mensagem.eml            um arquivo
    python -m analisador pasta\\                  todos os .eml da pasta
    python -m analisador mensagem.eml --nao-gravar

No Gmail: abra o e-mail > tres pontinhos > "Fazer download da mensagem".
No Outlook: arraste o e-mail para uma pasta do Windows.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console
from rich.text import Text

from analisador.analise import analisar_mensagem
from analisador.banco import gravar
from analisador.leitura import ler
from analisador.tela import relatorio
from monitor import banco as banco_monitor
from monitor.painel import COR_ALERTA, COR_ROTULO

console = Console()


def _arquivos(caminhos: list[str]) -> list[Path]:
    lista: list[Path] = []
    for c in map(Path, caminhos):
        lista += sorted(c.glob("*.eml")) if c.is_dir() else [c]
    return lista


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m analisador", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("caminhos", nargs="+", help="arquivos .eml ou pastas")
    parser.add_argument("--nao-gravar", action="store_true", help="só mostra, não grava no banco")
    args = parser.parse_args()

    try:
        conn = banco_monitor.conectar()
        marcas = banco_monitor.carregar_marcas(conn)
    except Exception:
        from monitor.__main__ import _marcas_e_conexao
        marcas, conn = _marcas_e_conexao()

    arquivos = _arquivos(args.caminhos)
    if not arquivos:
        console.print(Text("Nenhum arquivo .eml encontrado.", style=COR_ROTULO))
        return

    for arquivo in arquivos:
        if not arquivo.is_file():
            console.print(Text(f"Arquivo não encontrado: {arquivo}", style=COR_ALERTA))
            continue
        analise = analisar_mensagem(ler(arquivo), marcas, conn=conn)
        gravado = None
        if not args.nao_gravar:
            try:
                gravar(conn, analise, marcas) if conn else None
                gravado = conn is not None
            except Exception:
                gravado = False
        console.print(Text(str(arquivo), style=COR_ROTULO))
        console.print(relatorio(analise, gravado))
        console.print()


if __name__ == "__main__":
    main()
