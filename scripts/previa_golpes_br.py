"""Gera docs/imagens/sms-*.svg e email-boleto-pix.svg com os exemplos ficticios.

    python scripts/previa_golpes_br.py
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from rich.console import Console  # noqa: E402

from analisador.analise import analisar_mensagem  # noqa: E402
from analisador.leitura import ler  # noqa: E402
from analisador.tela import relatorio as relatorio_email  # noqa: E402
from mensagem.analise import analisar  # noqa: E402
from mensagem.tela import relatorio as relatorio_mensagem  # noqa: E402
from scripts.previa_painel import BRADESCO  # noqa: E402

MENSAGENS = {
    "sms-compra-falsa": ("BRADESCO: Compra aprovada de R$ 1.890,00 no cartao final 4421. Nao reconhece? "
                         "Acesse bradesco-cancelar.top/c ou ligue 0800 591 2233", "sms", "11987654321"),
    "sms-falso-parente": ("Oi mae, mudei de numero, salva esse aqui. Preciso pagar um boleto hoje, "
                          "me passa um pix pra mim? Te devolvo amanha", "whatsapp", "+55 11 91234-5678"),
    "sms-legitimo": ("Bradesco: seu codigo de seguranca e 482913. Nao compartilhe com ninguem.", "sms", "27888"),
}


def salvar(renderizavel, nome: str, titulo: str) -> None:
    console = Console(record=True, width=100, force_terminal=True, color_system="truecolor")
    console.print(renderizavel)
    destino = RAIZ / "docs" / "imagens" / f"{nome}.svg"
    console.save_svg(str(destino), title=titulo)
    print(destino)


def main() -> None:
    for nome, (texto, canal, de) in MENSAGENS.items():
        salvar(relatorio_mensagem(analisar(texto, [BRADESCO], canal, de)), nome,
               "Radar Phishing — SMS e WhatsApp")
    a = analisar_mensagem(ler(RAIZ / "tests" / "exemplos" / "golpe_boleto_pix.eml"), [BRADESCO],
                          politica_dmarc=lambda d: None, verificar_dkim=lambda m: None)
    salvar(relatorio_email(a), "email-boleto-pix", "Radar Phishing — boleto e Pix")


if __name__ == "__main__":
    main()
