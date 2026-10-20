"""Le QR Codes de imagens e PDFs e o texto de PDFs, tudo em memoria.

Por que isso importa: filtros de e-mail leem texto e links, mas nao imagem.
O golpista coloca o link (ou o Pix) dentro de um QR Code numa imagem ou num
PDF anexo, e o filtro deixa passar.

Nenhum arquivo e salvo em disco nem aberto por programa externo: imagem e
PDF sao lidos como bytes por bibliotecas Python (Pillow, zxing-cpp, pypdf).
"""

from __future__ import annotations

import io
import logging

# Imagem gigante pode ser uma "bomba de descompressao" (poucos KB que viram
# gigabytes na memoria). Acima disso, a imagem e ignorada: o PC e fraco.
LIMITE_PIXELS = 25_000_000
LIMITE_PAGINAS_PDF = 20

logging.getLogger("pypdf").setLevel(logging.ERROR)   # PDFs de golpe vivem quebrados


def qrcodes_em_imagem(dados: bytes) -> list[str]:
    try:
        import zxingcpp
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = LIMITE_PIXELS
        with Image.open(io.BytesIO(dados)) as img:
            img.load()
            if img.width * img.height > LIMITE_PIXELS:
                return []
            imagem = img.convert("RGB")
        lidos = zxingcpp.read_barcodes(imagem, formats=zxingcpp.BarcodeFormat.QRCode)
        return [r.text for r in lidos if r.text]
    except Exception:
        return []   # imagem corrompida, formato desconhecido ou bomba: nao derruba a analise


def _pdf(dados: bytes):
    from pypdf import PdfReader
    return PdfReader(io.BytesIO(dados))


def texto_de_pdf(dados: bytes) -> str:
    try:
        leitor = _pdf(dados)
        return "\n".join((p.extract_text() or "") for p in leitor.pages[:LIMITE_PAGINAS_PDF])
    except Exception:
        return ""


def qrcodes_em_pdf(dados: bytes) -> list[str]:
    textos: list[str] = []
    try:
        leitor = _pdf(dados)
        for pagina in leitor.pages[:LIMITE_PAGINAS_PDF]:
            for imagem in pagina.images:
                textos += qrcodes_em_imagem(imagem.data)
    except Exception:
        pass
    return list(dict.fromkeys(textos))


def eh_pdf(nome: str, tipo: str, dados: bytes) -> bool:
    return dados[:5] == b"%PDF-" or tipo == "application/pdf" or nome.lower().endswith(".pdf")


def eh_imagem(nome: str, tipo: str, dados: bytes) -> bool:
    assinaturas = (b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"BM", b"RIFF")
    return tipo.startswith("image/") or dados[:4].startswith(assinaturas) or \
        nome.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"))
