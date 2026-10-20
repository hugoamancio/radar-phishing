"""Pesquisa de um endereco suspeito: ja esta no banco? Parece golpe?

Nunca acessa o endereco pesquisado. So le o texto digitado, consulta o banco
e, se o dominio for desconhecido, roda o detector na hora.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit

from monitor.detector import Deteccao, Marca, analisar
from monitor.normalizacao import limpar
from risco.modelo import Avaliacao, calcular

# Resultados possiveis, do mais grave ao mais tranquilo.
CONHECIDO = "conhecido"            # o proprio dominio esta no banco
CONHECIDO_PAI = "conhecido_pai"    # um dominio "acima" dele esta no banco
SUSPEITO_AGORA = "suspeito_agora"  # nao esta no banco, mas o detector acusa
OFICIAL = "oficial"
NADA = "nada"


@dataclass
class Registro:
    """Uma linha do banco sobre um dominio suspeito."""
    dominio: str
    marca: str
    tecnicas: list[str]
    motivos: list[dict]
    trecho: str
    detectado_em: datetime
    certificados: int
    ultimo_emissor: str | None
    ultimo_certificado_em: datetime | None
    emails: int
    nota: int | None = None
    nivel: str | None = None
    motivos_risco: list[dict] | None = None
    mensagens: int = 0


@dataclass
class Resultado:
    entrada: str
    dominio: str | None
    tipo: str
    registro: Registro | None = None
    deteccoes: list[Deteccao] = field(default_factory=list)
    marca_oficial: str | None = None
    banco_ok: bool = True

    @property
    def risco(self) -> Avaliacao | None:
        """Nota do dominio: a do banco recalculada pelo modelo atual, ou a da analise na hora."""
        if self.registro:
            return calcular(self.registro.tecnicas)
        if self.deteccoes:
            return calcular(self.deteccoes[0].tecnicas)
        return None


def extrair_dominio(entrada: str) -> str | None:
    """Tira o dominio de uma URL, de um dominio solto ou de um endereco "desarmado".

    Aceita https://site.com/caminho?x=1, site.com:443, usuario@site.com e a
    notacao que analistas usam para nao gerar link clicavel: hxxps://site[.]com.
    Dominio com acento ou letra estrangeira vira punycode, que e como os
    certificados e o banco o guardam.
    """
    texto = entrada.strip().strip("<>\"'")
    if not texto:
        return None
    texto = re.sub(r"^hxxp", "http", texto, flags=re.IGNORECASE)
    texto = re.sub(r"\[\.\]|\(\.\)|\{\.\}|\[dot\]", ".", texto, flags=re.IGNORECASE)
    if "://" not in texto:
        texto = "http://" + texto
    try:
        host = urlsplit(texto).hostname
    except ValueError:
        return None
    if not host:
        return None
    host = limpar(host)
    if not host.isascii():
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError:
            return None
    if "." not in host or not re.fullmatch(r"[a-z0-9.\-]+", host):
        return None
    return host


def dominios_acima(dominio: str) -> list[str]:
    """login.seguro.golpe.xyz -> [seguro.golpe.xyz, golpe.xyz]. Para em 2 rotulos."""
    rotulos = dominio.split(".")
    return [".".join(rotulos[i:]) for i in range(1, len(rotulos) - 1)]


_CONSULTA = """
SELECT d.nome, m.nome, dd.tecnicas, dd.motivos, dd.trecho, dd.detectado_em,
       (SELECT count(*) FROM certificado c WHERE c.dominio_id = d.id),
       ult.emissor, ult.emitido_em,
       (SELECT count(DISTINCT le.email_id) FROM link_email le WHERE le.dominio_id = d.id),
       r.nota, r.nivel, r.motivos,
       (SELECT count(DISTINCT lm.mensagem_id) FROM link_mensagem lm WHERE lm.dominio_id = d.id)
FROM dominio d
JOIN deteccao_dominio dd ON dd.dominio_id = d.id
JOIN marca m ON m.id = dd.marca_id
LEFT JOIN LATERAL (
    SELECT emissor, emitido_em FROM certificado
    WHERE dominio_id = d.id ORDER BY visto_em DESC LIMIT 1
) ult ON true
LEFT JOIN vw_risco_atual r ON r.dominio_id = d.id AND r.email_id IS NULL
WHERE d.nome = %s
"""


def buscar_registro(conn, dominio: str) -> Registro | None:
    linha = conn.execute(_CONSULTA, (dominio,)).fetchone()
    return Registro(*linha) if linha else None


def pesquisar(entrada: str, marcas: list[Marca], conn=None) -> Resultado:
    dominio = extrair_dominio(entrada)
    if dominio is None:
        return Resultado(entrada, None, NADA)

    for marca in marcas:
        if marca.eh_oficial(dominio):
            return Resultado(entrada, dominio, OFICIAL, marca_oficial=marca.nome, banco_ok=conn is not None)

    if conn is not None:
        try:
            registro = buscar_registro(conn, dominio)
            if registro:
                return Resultado(entrada, dominio, CONHECIDO, registro=registro)
            for acima in dominios_acima(dominio):
                registro = buscar_registro(conn, acima)
                if registro:
                    return Resultado(entrada, dominio, CONHECIDO_PAI, registro=registro)
        except Exception:
            conn = None

    deteccoes = analisar(dominio, marcas)
    tipo = SUSPEITO_AGORA if deteccoes else NADA
    return Resultado(entrada, dominio, tipo, deteccoes=deteccoes, banco_ok=conn is not None)
