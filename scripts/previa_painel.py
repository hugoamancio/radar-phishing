"""Gera docs/imagens/painel-*.svg: o painel com detecoes de exemplo, sem rede nem banco.

    python scripts/previa_painel.py

Serve para revisar o visual e ilustrar o README. Os dominios sao inventados
para demonstrar cada tecnica; nao sao golpes reais.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from rich.console import Console  # noqa: E402

from monitor.detector import Marca, analisar  # noqa: E402
from monitor.painel import TECNICAS_REFORCO, Estado, LinhaDeteccao, Painel  # noqa: E402
from risco.modelo import calcular  # noqa: E402

BRADESCO = Marca(1, "Bradesco", ("bradesco.com.br", "bradesco", "bradescoseguros.com.br", "next.me"),
                 ("bradesco", "bradesc0", "bradescco", "bradesko", "bradesconet"), "237")

EXEMPLOS = [
    ("bradesco.com.br.acesso-seguro.xyz", "Let's Encrypt"),
    ("brаdesco-login.com".encode("idna").decode(), "Google Trust Services"),
    ("bardesco-token.top", "Let's Encrypt"),
    ("br4desco-app.online", "ZeroSSL"),
    ("x7k2.bradesco.support.entregarapida.click", "Let's Encrypt"),
    ("atualizacao-bradesco-pix.com", "Let's Encrypt"),
]


def estado_exemplo() -> Estado:
    e = Estado()
    e.inicio = time.monotonic() - 2 * 3600 - 17 * 60 - 42
    e.status = "conectado"
    e.certificados, e.dominios = 11_482_337, 19_604_115
    e.suspeitos_total, e.suspeitos_sessao = 37, 5
    e.ultima_deteccao = time.monotonic() - 95
    for i, v in enumerate(range(60)):
        e.por_segundo.append(1250 + (i * 37) % 420)
    agora = datetime.now()
    for i, (dominio, emissor) in enumerate(EXEMPLOS):
        det = analisar(dominio, [BRADESCO])[0]
        risco = calcular(det.tecnicas)
        e.deteccoes.append(LinhaDeteccao(
            agora - timedelta(minutes=2 + i * 11), det.dominio, det.trecho, det.principal,
            [t for t in det.tecnicas if t in TECNICAS_REFORCO], emissor, risco.nota, risco.nivel))
    return e


def main() -> None:
    destino = RAIZ / "docs" / "imagens"
    destino.mkdir(parents=True, exist_ok=True)
    estado = estado_exemplo()
    for nome, largura, altura in (("largo", 150, 34), ("estreito", 90, 44), ("compacto", 60, 44)):
        console = Console(record=True, width=largura, height=altura, force_terminal=True,
                          color_system="truecolor")
        console.print(Painel(estado, ["Bradesco"]), height=altura)
        arquivo = destino / f"painel-{nome}.svg"
        console.save_svg(str(arquivo), title="Radar Phishing — monitor de domínios")
        print(arquivo)


if __name__ == "__main__":
    main()
