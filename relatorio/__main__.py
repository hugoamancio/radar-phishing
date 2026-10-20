"""Relatorio de inteligencia: campanhas, tecnicas, infraestrutura e indicadores.

    python -m relatorio              ultimos 7 dias, em dados/relatorios/
    python -m relatorio --dias 30
    python -m relatorio --abrir      abre o relatorio no navegador ao terminar

Gera tres arquivos: o relatorio (HTML), os indicadores em CSV e em STIX 2.1.
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console  # noqa: E402
from rich.table import Table  # noqa: E402
from rich.text import Text  # noqa: E402

from monitor import banco  # noqa: E402
from monitor.cores import COR_BORDA, COR_DESTAQUE, COR_ROTULO  # noqa: E402
from relatorio import iocs, pagina  # noqa: E402
from relatorio.coleta import coletar  # noqa: E402

PASTA = Path(__file__).resolve().parent.parent / "dados" / "relatorios"


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m relatorio", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dias", type=int, default=7)
    parser.add_argument("--saida", type=Path, default=PASTA)
    parser.add_argument("--abrir", action="store_true")
    args = parser.parse_args()

    console = Console()
    dados = coletar(banco.conectar(), args.dias)
    args.saida.mkdir(parents=True, exist_ok=True)
    nome = f"{datetime.now():%Y-%m-%d_%H%M}"
    arquivos = {
        "Relatório": (args.saida / f"relatorio_{nome}.html", pagina.montar(dados)),
        "IOCs (CSV)": (args.saida / f"iocs_{nome}.csv", iocs.csv_texto(dados)),
        "IOCs (STIX 2.1)": (args.saida / f"iocs_{nome}.stix.json", iocs.stix_texto(dados)),
    }
    for caminho, conteudo in arquivos.values():
        caminho.write_text(conteudo, encoding="utf-8")

    console.print(Text.assemble(("Radar Phishing", "bold white"), ("  ·  ", COR_BORDA),
                                ("Relatório de inteligência", COR_DESTAQUE),
                                (f"   últimos {args.dias} dias", COR_ROTULO)))
    tabela = Table(box=None, show_header=False, padding=(0, 2))
    tabela.add_row("Domínios suspeitos", str(len(dados.deteccoes)))
    tabela.add_row("Campanhas", str(sum(c.e_campanha for c in dados.campanhas)))
    tabela.add_row("Indicadores exportados", str(len(iocs.linhas(dados))))
    for rotulo, (caminho, _) in arquivos.items():
        tabela.add_row(rotulo, Text(str(caminho), style=COR_ROTULO))
    console.print(tabela)
    if args.abrir:
        webbrowser.open(arquivos["Relatório"][0].resolve().as_uri())


if __name__ == "__main__":
    main()
