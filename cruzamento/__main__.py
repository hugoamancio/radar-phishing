"""Mostra quais golpes o monitor ja conhecia antes de chegarem por e-mail ou mensagem.

    python -m cruzamento
"""

from __future__ import annotations

from rich.console import Console
from rich.text import Text

from cruzamento.consulta import ler, resumir
from cruzamento.tela import TelaCruzamento
from monitor import banco
from monitor.cores import COR_ALERTA


def main() -> None:
    console = Console()
    try:
        conn = banco.conectar()
    except Exception:
        console.print(Text("Banco indisponível. Ligue com: docker compose up -d --wait", style=COR_ALERTA))
        return
    itens = ler(conn)
    console.print(TelaCruzamento(itens, resumir(itens)))


if __name__ == "__main__":
    main()
