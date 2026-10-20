"""Le o "Pix copia e cola" (BR Code, padrao EMV do Banco Central).

Um QR Code de Pix e so um texto como este:

    00020126580014br.gov.bcb.pix0136 <chave> ... 5913FULANO DE TAL6009SAO PAULO ... 6304ABCD

Cada campo e ID (2 digitos) + TAMANHO (2 digitos) + VALOR. Os que importam:

    26  conta do recebedor; dentro: 00 = "br.gov.bcb.pix", 01 = chave, 25 = URL (Pix dinamico)
    54  valor          59  nome do recebedor          60  cidade
    62  dados extras; dentro: 05 = identificador da transacao
    63  CRC16: conferencia do texto inteiro

O ponto do golpe: o e-mail diz "pague sua fatura do Bradesco", mas o QR Code
leva o dinheiro para "FULANO DE TAL". O nome do recebedor esta no proprio
codigo, e o app do banco o mostra so na ultima tela, quando muita gente ja
nem le.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Pix:
    texto: str
    crc_ok: bool
    chave: str | None = None
    url: str | None = None              # Pix dinamico: o app busca os dados nesta URL
    recebedor: str | None = None
    cidade: str | None = None
    valor: float | None = None
    txid: str | None = None
    problemas: list[str] = field(default_factory=list)

    @property
    def tipo_chave(self) -> str | None:
        c = self.chave or ""
        digitos = "".join(ch for ch in c if ch.isdigit())
        if not c:
            return None
        if "@" in c:
            return "e-mail"
        if c.startswith("+55"):
            return "telefone"
        if len(c) == 36 and c.count("-") == 4:
            return "chave aleatória"
        if len(digitos) == 11 and digitos == c:
            return "CPF"
        if len(digitos) == 14 and digitos == c:
            return "CNPJ"
        return "outra"


def crc16(texto: str) -> str:
    """CRC16/CCITT-FALSE (polinomio 0x1021, inicio 0xFFFF), em 4 digitos hexadecimais."""
    crc = 0xFFFF
    for byte in texto.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return f"{crc:04X}"


def _campos(texto: str) -> dict[str, str] | None:
    campos, i = {}, 0
    while i < len(texto):
        if i + 4 > len(texto) or not texto[i:i + 4].isdigit():
            return None
        ident, tamanho = texto[i:i + 2], int(texto[i + 2:i + 4])
        valor = texto[i + 4:i + 4 + tamanho]
        if len(valor) != tamanho:
            return None
        campos[ident] = valor
        i += 4 + tamanho
    return campos


def parece_pix(texto: str) -> bool:
    t = (texto or "").strip()
    return t.startswith("000201") and "br.gov.bcb.pix" in t.lower()


def ler(texto: str) -> Pix | None:
    """Abre um BR Code. None se o texto nao for um Pix."""
    t = (texto or "").strip()
    if not parece_pix(t):
        return None
    campos = _campos(t)
    if campos is None:
        return Pix(t, False, problemas=["estrutura do código Pix inválida"])

    crc_ok = "63" in campos and t.endswith(campos["63"]) and crc16(t[:-4]) == campos["63"].upper()
    pix = Pix(t, crc_ok)
    if not crc_ok:
        pix.problemas.append("conferência (CRC) não bate: o código foi alterado ou está corrompido")

    conta = next((v for k, v in campos.items() if "26" <= k <= "51" and "br.gov.bcb.pix" in v.lower()), None)
    if conta:
        sub = _campos(conta) or {}
        pix.chave = sub.get("01")
        pix.url = sub.get("25")
    pix.recebedor = campos.get("59")
    pix.cidade = campos.get("60")
    if campos.get("54"):
        try:
            pix.valor = float(campos["54"])
        except ValueError:
            pix.problemas.append("valor ilegível")
    extra = _campos(campos.get("62", "")) or {}
    pix.txid = extra.get("05")
    return pix


def montar(chave: str, recebedor: str, cidade: str, valor: float | None = None, txid: str = "***") -> str:
    """Monta um BR Code estatico valido. Usado pelos testes e pelos exemplos."""
    def campo(ident: str, valor_: str) -> str:
        return f"{ident}{len(valor_):02d}{valor_}"

    conta = campo("00", "br.gov.bcb.pix") + campo("01", chave)
    corpo = (campo("00", "01") + campo("26", conta) + campo("52", "0000") + campo("53", "986")
             + (campo("54", f"{valor:.2f}") if valor is not None else "")
             + campo("58", "BR") + campo("59", recebedor[:25]) + campo("60", cidade[:15])
             + campo("62", campo("05", txid)) + "6304")
    return corpo + crc16(corpo)


def encontrar_em_texto(texto: str) -> list[str]:
    """Codigos Pix copia e cola dentro de um texto qualquer.

    Uma expressao regular nao basta: o codigo tem espacos (no nome do
    recebedor) e pode conter "6304" no meio de uma chave. Por isso, a partir
    de cada "000201", os campos sao percorridos um a um ate o campo 63 (CRC).
    """
    achados: list[str] = []
    inicio = (texto or "").find("000201")
    while inicio != -1:
        i = inicio
        while i + 4 <= len(texto) and texto[i:i + 4].isdigit():
            ident, tamanho = texto[i:i + 2], int(texto[i + 2:i + 4])
            fim = i + 4 + tamanho
            if fim > len(texto):
                break
            if ident == "63":
                candidato = texto[inicio:fim]
                if parece_pix(candidato):
                    achados.append(candidato)
                break
            i = fim
        inicio = texto.find("000201", inicio + 1)
    return achados
