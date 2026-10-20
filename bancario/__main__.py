"""Confere boleto, Pix e QR Code avulsos.

    python -m bancario boleto "23791.23454 67890.123457 67890.123457 6 16150000189000"
    python -m bancario pix "00020126...6304ABCD"
    python -m bancario qrcode imagem.png        (ou um PDF)

Nada e acessado na internet: tudo e conferido localmente.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from bancario import arquivos, boleto, pix
from bancario.tela import bloco_boleto, bloco_pix
from monitor.cores import COR_ALERTA, COR_BORDA, COR_OK, COR_ROTULO
from monitor.detector import NOMES_TECNICAS
from monitor.pesquisa import extrair_dominio

console = Console()


def _painel(corpo, ok: bool, titulo: str) -> Panel:
    return Panel(corpo, title=titulo, title_align="left", box=box.ROUNDED,
                 border_style=COR_OK if ok else COR_ALERTA, padding=(1, 2))


def cmd_boleto(linha: str) -> None:
    b = boleto.conferir(linha)
    if b is None:
        console.print(Text("Não reconheci uma linha digitável: são 47 dígitos (boleto) ou 48 (conta de consumo).",
                           style=COR_ROTULO))
        return
    titulo = "Boleto confere" if b.valido else "Boleto com linha adulterada"
    console.print(_painel(bloco_boleto(b, "linha informada"), b.valido, titulo))
    if b.valido:
        console.print(Text("Os dígitos de conferência batem. Isso não garante que o boleto é legítimo: "
                           "confira se o banco e o beneficiário são quem você espera.", style=COR_ROTULO))


def cmd_pix(codigo: str) -> None:
    p = pix.ler(codigo)
    if p is None:
        console.print(Text("Não é um Pix copia e cola (deve começar com 000201 e conter br.gov.bcb.pix).",
                           style=COR_ROTULO))
        return
    console.print(_painel(bloco_pix(p, "código informado", False), p.crc_ok,
                          "Código Pix confere" if p.crc_ok else "Código Pix alterado"))
    console.print(Text("Antes de pagar, confira se o recebedor acima é mesmo quem você quer pagar.", style=COR_ROTULO))


def cmd_qrcode(caminho: str) -> None:
    arquivo = Path(caminho)
    if not arquivo.is_file():
        console.print(Text(f"Arquivo não encontrado: {arquivo}", style=COR_ALERTA))
        return
    dados = arquivo.read_bytes()
    if arquivos.eh_pdf(arquivo.name, "", dados):
        codigos = arquivos.qrcodes_em_pdf(dados)
    else:
        codigos = arquivos.qrcodes_em_imagem(dados)
    if not codigos:
        console.print(Text("Nenhum QR Code encontrado no arquivo.", style=COR_ROTULO))
        return
    from monitor.__main__ import _marcas_e_conexao
    from monitor.detector import analisar

    marcas, _ = _marcas_e_conexao()
    for conteudo in codigos:
        p = pix.ler(conteudo)
        if p:
            cmd_pix(conteudo)
            continue
        dominio = extrair_dominio(conteudo)
        deteccoes = analisar(dominio, marcas) if dominio else []
        corpo = Text.assemble(("Conteúdo  ", COR_ROTULO), (conteudo, "white"))
        if dominio:
            corpo.append("\nDestino   ", style=COR_ROTULO)
            corpo.append(dominio, style=COR_ALERTA if deteccoes else COR_OK)
        for d in deteccoes:
            corpo.append(f"\n\nImita o {d.marca.nome}: "
                         + ", ".join(NOMES_TECNICAS[m['tecnica']] for m in d.motivos), style=COR_ALERTA)
        console.print(_painel(corpo, not deteccoes, "QR Code suspeito" if deteccoes else "QR Code lido"))
    console.print(Text("O link não foi acessado: só lido.", style=COR_BORDA))


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m bancario", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("boleto", help="confere uma linha digitável").add_argument("linha")
    sub.add_parser("pix", help="abre um Pix copia e cola").add_argument("codigo")
    sub.add_parser("qrcode", help="lê QR Codes de uma imagem ou PDF").add_argument("arquivo")
    args = parser.parse_args()
    if args.comando == "boleto":
        cmd_boleto(args.linha)
    elif args.comando == "pix":
        cmd_pix(args.codigo)
    else:
        cmd_qrcode(args.arquivo)


if __name__ == "__main__":
    main()
