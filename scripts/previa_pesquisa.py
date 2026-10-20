"""Gera docs/imagens/pesquisa.svg: um cartao de cada resultado possivel da pesquisa.

    python scripts/previa_pesquisa.py

Os enderecos sao ficticios; o registro "conhecido" e montado na mao, sem banco.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from rich.console import Console  # noqa: E402

from monitor.pesquisa import CONHECIDO, Registro, Resultado, pesquisar  # noqa: E402
from monitor.tela_pesquisa import cartao  # noqa: E402
from scripts.previa_painel import BRADESCO  # noqa: E402


def main() -> None:
    agora = datetime.now(timezone.utc)
    conhecido = Resultado(
        entrada="https://bradesco-pix-seguro.xyz/atualizar?cliente=8812",
        dominio="bradesco-pix-seguro.xyz",
        tipo=CONHECIDO,
        registro=Registro(
            dominio="bradesco-pix-seguro.xyz", marca="Bradesco",
            tecnicas=["marca_no_dominio", "palavra_isca", "tld_suspeito"],
            motivos=[{"tecnica": "marca_no_dominio", "detalhe": 'contém "bradesco"'},
                     {"tecnica": "palavra_isca", "detalhe": "termos de golpe: pix, seguro"},
                     {"tecnica": "tld_suspeito", "detalhe": 'terminação ".xyz", comum em golpes'}],
            trecho="bradesco", detectado_em=agora - timedelta(days=3, hours=2),
            certificados=2, ultimo_emissor="Let's Encrypt",
            ultimo_certificado_em=agora - timedelta(days=1), emails=0),
    )
    resultados = [conhecido] + [pesquisar(e, [BRADESCO]) for e in (
        "hxxps://bardesco-token[.]top/login", "https://www.bradesco.com.br", "https://exemplo.org/promocao")]
    for r in resultados:
        r.banco_ok = True  # a previa roda sem banco; o aviso de banco fora do ar nao vale aqui
    cartoes = [cartao(r) for r in resultados]
    console = Console(record=True, width=96, force_terminal=True, color_system="truecolor")
    for c in cartoes:
        console.print(c)
        console.print()
    destino = RAIZ / "docs" / "imagens" / "pesquisa.svg"
    console.save_svg(str(destino), title="Radar Phishing — pesquisa de endereço")
    print(destino)


if __name__ == "__main__":
    main()
