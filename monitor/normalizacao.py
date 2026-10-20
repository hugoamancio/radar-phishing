"""Desfaz os disfarces que golpistas usam para imitar uma marca num dominio.

Um dominio como ``brаdesc0-app.com`` (com "а" cirilico e zero no lugar do
"o") nao contem a palavra "bradesco" quando comparado letra a letra. Antes de
procurar a marca, o texto passa por tres camadas de normalizacao:

1. IDN: rotulos ``xn--...`` (punycode) viram o Unicode que o usuario ve.
2. Homoglifos Unicode: letras de outros alfabetos que parecem latinas.
3. Leet e combinacoes visuais: 0 -> o, rn -> m, vv -> w...
"""

from __future__ import annotations

import unicodedata

# Letras de outros alfabetos visualmente identicas as latinas. Lista focada nas
# que de fato aparecem em ataques de homografo (cirilico e grego, sobretudo).
HOMOGLIFOS = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
    "ѕ": "s", "і": "i", "ј": "j", "ԁ": "d", "ӏ": "l", "һ": "h", "ԛ": "q",
    "ԝ": "w", "ɡ": "g", "ı": "i", "ɑ": "a", "ο": "o", "α": "a", "ν": "v",
    "ρ": "p", "τ": "t", "κ": "k", "ι": "i",
})

# Digitos e simbolos que substituem letras. O "1" e ambiguo (l ou i), entao
# gera duas variantes em vez de escolher uma.
LEET_BASE = str.maketrans({"0": "o", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})

# Pares de letras que, juntos, parecem outra letra.
COMBINACOES = (("rn", "m"), ("vv", "w"), ("cl", "d"), ("nn", "m"))


def limpar(dominio: str) -> str:
    """Minusculas, sem curinga ``*.`` e sem ponto final."""
    dominio = dominio.strip().lower().rstrip(".")
    if dominio.startswith("*."):
        dominio = dominio[2:]
    return dominio


def decodificar_idn(dominio: str) -> str:
    """Converte rotulos punycode (``xn--``) no texto Unicode que o navegador exibe."""
    rotulos = []
    for rotulo in dominio.split("."):
        if rotulo.startswith("xn--"):
            try:
                rotulo = rotulo.encode("ascii").decode("idna")
            except UnicodeError:
                pass  # punycode invalido: mantem como veio
        rotulos.append(rotulo)
    return ".".join(rotulos)


def tirar_acentos(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def variantes(dominio: str) -> set[str]:
    """Todas as leituras "desdisfarcadas" de um dominio ja limpo.

    Devolve um conjunto pequeno (no maximo 4 strings). A primeira camada
    (Unicode -> latino) e sempre aplicada; leet e combinacoes geram variantes
    porque podem corromper dominios legitimos (ex.: "clube" -> "dube").
    """
    base = tirar_acentos(decodificar_idn(dominio).translate(HOMOGLIFOS))
    leet = base.translate(LEET_BASE)
    resultado = {base}
    for um_vira in ("l", "i"):
        v = leet.replace("1", um_vira)
        resultado.add(v)
        for de, para in COMBINACOES:
            v = v.replace(de, para)
        resultado.add(v)
    return resultado


def tokens(dominio: str) -> list[str]:
    """Partes do dominio separadas por ponto e hifen: ``app-bradesco.com`` -> app, bradesco, com."""
    return [t for t in dominio.replace("-", ".").split(".") if t]


def tem_disfarce(dominio_limpo: str) -> bool:
    """Indica se o dominio usa Unicode/punycode, ou seja, pode enganar visualmente."""
    return "xn--" in dominio_limpo or not dominio_limpo.isascii()


# Segundo nivel usado por varios paises: em bradesco.com.br o dominio
# "organizacional" tem 3 partes, nao 2.
SEGUNDO_NIVEL = {"com", "net", "org", "gov", "edu", "mil", "co", "ac", "art", "blog", "app", "tur", "inf"}


def dominio_organizacional(dominio: str) -> str:
    """mail.bradesco.com.br -> bradesco.com.br; envio.golpe.xyz -> golpe.xyz."""
    partes = dominio.lower().strip(".").split(".")
    if len(partes) >= 3 and len(partes[-1]) == 2 and partes[-2] in SEGUNDO_NIVEL:
        return ".".join(partes[-3:])
    return ".".join(partes[-2:])
