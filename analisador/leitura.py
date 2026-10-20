"""Le um arquivo .eml e separa o que interessa para a analise.

So a biblioteca padrao (``email``). O corpo e lido para a analise, mas nunca
e gravado no banco: ver analisador/banco.py.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path


@dataclass
class Anexo:
    nome: str
    tipo: str
    tamanho: int
    dados: bytes = b""      # so em memoria: usado para ler boleto e QR Code, nunca gravado


@dataclass
class Mensagem:
    bruto: bytes                       # arquivo inteiro, necessario para verificar o DKIM
    sha256: str                        # identifica o arquivo sem guardar o conteudo
    remetente_nome: str
    remetente_endereco: str
    reply_to: str | None
    return_path: str | None
    assunto: str
    recebido_em: datetime | None
    message_id: str | None
    texto: str
    html: str
    anexos: list[Anexo] = field(default_factory=list)
    imagens: list[Anexo] = field(default_factory=list)   # imagens no corpo (QR Code costuma vir aqui)
    cabecalhos: EmailMessage | None = None

    @property
    def dominio_remetente(self) -> str:
        return self.remetente_endereco.rpartition("@")[2].lower()


def _endereco(valor: str | None) -> tuple[str, str]:
    if not valor:
        return "", ""
    pares = getaddresses([str(valor)])
    return pares[0] if pares else ("", "")


def ler(origem: Path | bytes) -> Mensagem:
    bruto = origem if isinstance(origem, bytes) else Path(origem).read_bytes()
    msg: EmailMessage = BytesParser(policy=policy.default).parsebytes(bruto)

    nome, endereco = _endereco(msg.get("From"))
    _, reply = _endereco(msg.get("Reply-To"))
    _, retorno = _endereco(msg.get("Return-Path"))

    try:
        data = parsedate_to_datetime(msg["Date"]) if msg["Date"] else None
    except (TypeError, ValueError):
        data = None

    textos, htmls, anexos, imagens = [], [], [], []
    for parte in msg.walk():
        if parte.is_multipart():
            continue
        disposicao = parte.get_content_disposition()
        nome_arquivo = parte.get_filename()
        if disposicao == "attachment" or (nome_arquivo and disposicao != "inline"):
            carga = parte.get_payload(decode=True) or b""
            anexos.append(Anexo(nome_arquivo or "(sem nome)", parte.get_content_type(), len(carga), carga))
            continue
        if parte.get_content_maintype() == "image":
            carga = parte.get_payload(decode=True) or b""
            imagens.append(Anexo(nome_arquivo or "do corpo do e-mail",
                                 parte.get_content_type(), len(carga), carga))
            continue
        try:
            conteudo = parte.get_content()
        except (LookupError, UnicodeDecodeError):
            conteudo = (parte.get_payload(decode=True) or b"").decode("latin-1", "replace")
        if parte.get_content_type() == "text/html":
            htmls.append(conteudo)
        elif parte.get_content_type() == "text/plain":
            textos.append(conteudo)

    return Mensagem(
        bruto=bruto,
        sha256=hashlib.sha256(bruto).hexdigest(),
        remetente_nome=nome.strip(),
        remetente_endereco=endereco.strip().lower(),
        reply_to=reply.lower() or None,
        return_path=retorno.lower() or None,
        assunto=str(msg.get("Subject", "")).strip(),
        recebido_em=data,
        message_id=str(msg.get("Message-ID", "")).strip() or None,
        texto="\n".join(textos),
        html="\n".join(htmls),
        anexos=anexos,
        imagens=imagens,
        cabecalhos=msg,
    )
