"""Gera docs/imagens/email-*.svg: o relatorio dos e-mails de exemplo (ficticios).

    python scripts/previa_email.py
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from rich.console import Console  # noqa: E402

from analisador.analise import analisar_mensagem  # noqa: E402
from analisador.leitura import ler  # noqa: E402
from analisador.tela import relatorio  # noqa: E402
from scripts.previa_painel import BRADESCO  # noqa: E402

EXEMPLOS = RAIZ / "tests" / "exemplos"


def main() -> None:
    destino = RAIZ / "docs" / "imagens"
    for nome, arquivo in (("golpe", "golpe_dominio_parecido.eml"), ("falsificado", "golpe_falsifica_oficial.eml"),
                          ("legitimo", "legitimo.eml")):
        analise = analisar_mensagem(ler(EXEMPLOS / arquivo), [BRADESCO],
                                    politica_dmarc=lambda d: "reject" if d == "bradesco.com.br" else None,
                                    verificar_dkim=lambda m: None)
        console = Console(record=True, width=100, force_terminal=True, color_system="truecolor")
        console.print(relatorio(analise))
        saida = destino / f"email-{nome}.svg"
        console.save_svg(str(saida), title="Radar Phishing — análise de e-mail")
        print(saida)


if __name__ == "__main__":
    main()
