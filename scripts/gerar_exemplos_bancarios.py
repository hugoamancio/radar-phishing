"""Gera os exemplos FICTICIOS de boleto, Pix e QR Code usados nos testes.

    python scripts/gerar_exemplos_bancarios.py

Saidas em tests/exemplos/:
    golpe_boleto_pix.eml   e-mail "do Bradesco" com boleto de outro banco em PDF,
                           valor diferente do texto e QR Code de Pix para pessoa fisica
    boleto_legitimo.eml    e-mail do Bradesco com boleto 237 coerente com o texto
    qrcode_link.png        QR Code com link que imita o Bradesco

Nomes, chaves e dominios sao inventados. O CPF 123.456.789-09 e o exemplo
classico de CPF de formato valido usado em documentacao.
"""

from __future__ import annotations

import io
import sys
from datetime import date
from email.message import EmailMessage
from email.utils import format_datetime
from datetime import datetime, timezone, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import segno  # noqa: E402
from fpdf import FPDF  # noqa: E402

from bancario import boleto, pix  # noqa: E402

DESTINO = RAIZ / "tests" / "exemplos"
DATA = datetime(2026, 10, 20, 9, 30, tzinfo=timezone(timedelta(hours=-3)))

LINHA_GOLPE = boleto.montar("341", 1890.00, date(2026, 10, 30), "1098765432109876543210987")
LINHA_LEGITIMA = boleto.montar("237", 450.00, date(2026, 10, 30), "3381260000000000000000040")
PIX_GOLPE = pix.montar("12345678909", "JOSE CARLOS PEREIRA", "SAO PAULO", 450.00, "FATURA102026")


def png_qr(conteudo: str) -> bytes:
    saida = io.BytesIO()
    segno.make(conteudo, error="m").save(saida, kind="png", scale=6, border=4)
    return saida.getvalue()


def pdf_boleto(titulo: str, linha: str, valor: str) -> bytes:
    doc = FPDF()
    doc.add_page()
    doc.set_font("Helvetica", size=14)
    doc.cell(0, 10, titulo, new_x="LMARGIN", new_y="NEXT")
    doc.set_font("Helvetica", size=11)
    doc.cell(0, 8, "Documento ficticio para testes do Radar Phishing", new_x="LMARGIN", new_y="NEXT")
    doc.cell(0, 8, f"Valor do documento: R$ {valor}", new_x="LMARGIN", new_y="NEXT")
    doc.cell(0, 8, "Vencimento: 30/10/2026", new_x="LMARGIN", new_y="NEXT")
    doc.ln(6)
    doc.set_font("Courier", size=12)
    doc.cell(0, 8, boleto.conferir(linha).formatada, new_x="LMARGIN", new_y="NEXT")
    return bytes(doc.output())


def email_golpe() -> bytes:
    m = EmailMessage()
    m["From"] = '"Bradesco Cobranca" <cobranca@bradesco-faturas.top>'
    m["To"] = "cliente@exemplo.com"
    m["Subject"] = "Fatura do cartao Bradesco disponivel"
    m["Date"] = format_datetime(DATA)
    m["Message-ID"] = "<exemplo-ficticio-004@bradesco-faturas.top>"
    m["X-Exemplo"] = "e-mail ficticio criado para os testes do Radar Phishing"
    m["Authentication-Results"] = ("mx.google.com; spf=fail smtp.mailfrom=bradesco-faturas.top; dkim=none; "
                                   "dmarc=fail header.from=bradesco-faturas.top")
    texto = ("Prezado cliente, sua fatura do cartao Bradesco no valor de R$ 450,00 esta disponivel. "
             "Pague pelo boleto em anexo ou pelo QR Code Pix abaixo. (Mensagem ficticia para testes.)")
    m.set_content(texto)
    m.add_alternative(f"<html><body><p>{texto}</p><img src=\"cid:qrpix\"></body></html>", subtype="html")
    m.get_payload()[1].add_related(png_qr(PIX_GOLPE), maintype="image", subtype="png", cid="<qrpix>")
    m.add_attachment(pdf_boleto("Fatura Bradesco - 10/2026", LINHA_GOLPE, "1.890,00"),
                     maintype="application", subtype="pdf", filename="fatura_bradesco.pdf")
    return bytes(m)


def email_legitimo() -> bytes:
    m = EmailMessage()
    m["From"] = '"Bradesco" <faturas@bradesco.com.br>'
    m["To"] = "cliente@exemplo.com"
    m["Subject"] = "Sua fatura chegou"
    m["Date"] = format_datetime(DATA)
    m["Message-ID"] = "<exemplo-ficticio-005@bradesco.com.br>"
    m["X-Exemplo"] = "e-mail ficticio criado para os testes do Radar Phishing"
    m["Authentication-Results"] = ("mx.google.com; spf=pass smtp.mailfrom=retorno@bradesco.com.br; "
                                   "dkim=pass header.i=@bradesco.com.br; dmarc=pass header.from=bradesco.com.br")
    m.set_content("Olá! A fatura do seu cartão Bradesco, no valor de R$ 450,00, vence em 30/10/2026. "
                  f"Linha digitável: {boleto.conferir(LINHA_LEGITIMA).formatada} (Mensagem fictícia para testes.)")
    return bytes(m)


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    (DESTINO / "golpe_boleto_pix.eml").write_bytes(email_golpe())
    (DESTINO / "boleto_legitimo.eml").write_bytes(email_legitimo())
    (DESTINO / "qrcode_link.png").write_bytes(png_qr("https://bradesco-pontos.top/resgate"))
    print("linha golpe   ", boleto.conferir(LINHA_GOLPE).formatada)
    print("linha legitima", boleto.conferir(LINHA_LEGITIMA).formatada)
    print("pix golpe     ", PIX_GOLPE)


if __name__ == "__main__":
    main()
