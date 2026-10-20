"""Confere a linha digitavel de um boleto (padrao FEBRABAN).

O golpe do boleto falso troca alguns digitos da linha para o pagamento cair
em outra conta. A linha tem digitos de conferencia (DV), calculados a partir
dos outros digitos. Quem adultera sem refazer as contas deixa DV errado; quem
refaz as contas costuma mudar o banco, e o banco aparece nos 3 primeiros digitos.

Dois formatos:

Boleto bancario, 47 digitos (cobranca: contas, faturas, compras)

    AAABC.CCCCX  DDDDD.DDDDDY  EEEEE.EEEEEZ  K  UUUUVVVVVVVVVV
    AAA  banco (237 = Bradesco)          B  moeda (9 = real)
    X Y Z  DV de cada campo (modulo 10)  K  DV geral (modulo 11)
    UUUU fator de vencimento             V  valor em centavos

Arrecadacao, 48 digitos, comeca com 8 (agua, luz, telefone, tributos)

    4 blocos de 11 digitos + 1 DV cada. O 3o digito diz se o DV e modulo 10
    (6 ou 7) ou modulo 11 (8 ou 9).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

BANCOS = {
    "001": "Banco do Brasil", "033": "Santander", "077": "Banco Inter", "104": "Caixa",
    "212": "Banco Original", "237": "Bradesco", "260": "Nubank", "336": "C6 Bank",
    "341": "Itaú", "422": "Safra", "748": "Sicredi", "756": "Sicoob",
}

# O fator de vencimento conta dias. Ao chegar em 9999 (21/02/2025) ele voltou
# para 1000 (22/02/2025). Por isso cada fator tem duas datas possiveis; vale a
# mais proxima de hoje.
BASE_ANTIGA = date(1997, 10, 7)          # fator 0 na regra original
BASE_NOVA = date(2025, 2, 22)            # fator 1000 depois do reinicio

# Linha digitavel solta num texto: 47 ou 48 digitos, com pontos, espacos e hifens.
PADRAO_LINHA = re.compile(r"(?<!\d)(?:\d[\s.\-]*){46}\d(?:[\s.\-]*\d)?(?!\d)")


@dataclass
class Boleto:
    linha: str                          # so digitos
    tipo: str                           # "bancario" ou "arrecadacao"
    valido: bool
    problemas: list[str] = field(default_factory=list)
    banco_codigo: str | None = None
    banco_nome: str | None = None
    valor: float | None = None
    vencimento: date | None = None

    @property
    def formatada(self) -> str:
        l = self.linha
        if self.tipo == "bancario":
            return f"{l[0:5]}.{l[5:10]} {l[10:15]}.{l[15:21]} {l[21:26]}.{l[26:32]} {l[32]} {l[33:47]}"
        return " ".join(f"{l[i:i + 11]}-{l[i + 11]}" for i in range(0, 48, 12))


def modulo10(numero: str) -> int:
    """Pesos 2,1,2,1... da direita para a esquerda; produtos >= 10 somam os digitos."""
    soma = 0
    for i, d in enumerate(reversed(numero)):
        p = int(d) * (2 if i % 2 == 0 else 1)
        soma += p // 10 + p % 10
    return (10 - soma % 10) % 10


def modulo11_bancario(numero: str) -> int:
    """DV geral do boleto bancario: pesos 2 a 9 repetidos; resultado 0, 10 ou 11 vira 1."""
    soma = sum(int(d) * (2 + i % 8) for i, d in enumerate(reversed(numero)))
    dv = 11 - soma % 11
    return 1 if dv in (0, 10, 11) else dv


def modulo11_arrecadacao(numero: str) -> int:
    """DV de arrecadacao em modulo 11: resto 0 ou 1 vira 0; 10 vira 1."""
    soma = sum(int(d) * (2 + i % 8) for i, d in enumerate(reversed(numero)))
    resto = soma % 11
    if resto in (0, 1):
        return 0
    if resto == 10:
        return 1
    return 11 - resto


def codigo_de_barras(linha: str) -> str:
    """Remonta os 44 digitos do codigo de barras a partir da linha de 47."""
    return linha[0:4] + linha[32] + linha[33:47] + linha[4:9] + linha[10:20] + linha[21:31]


def vencimento_do_fator(fator: int, hoje: date | None = None) -> date | None:
    if fator == 0:
        return None                     # boleto sem vencimento
    hoje = hoje or date.today()
    candidatas = [BASE_ANTIGA + timedelta(days=fator)]
    if fator >= 1000:
        candidatas.append(BASE_NOVA + timedelta(days=fator - 1000))
    return min(candidatas, key=lambda d: abs((d - hoje).days))


def _conferir_bancario(l: str, hoje: date | None) -> Boleto:
    b = Boleto(l, "bancario", True, banco_codigo=l[0:3], banco_nome=BANCOS.get(l[0:3]))
    for nome, inicio, fim, dv in (("1º campo", 0, 9, 9), ("2º campo", 10, 20, 20), ("3º campo", 21, 31, 31)):
        if modulo10(l[inicio:fim]) != int(l[dv]):
            b.problemas.append(f"dígito de conferência do {nome} não confere")
    barras = codigo_de_barras(l)
    if modulo11_bancario(barras[:4] + barras[5:]) != int(barras[4]):
        b.problemas.append("dígito de conferência geral não confere")
    if l[3] != "9":
        b.problemas.append(f"código de moeda {l[3]} (o real é 9)")
    b.valido = not b.problemas
    b.valor = int(l[37:47]) / 100
    b.vencimento = vencimento_do_fator(int(l[33:37]), hoje)
    return b


def _conferir_arrecadacao(l: str) -> Boleto:
    b = Boleto(l, "arrecadacao", True)
    if l[2] not in "6789":
        b.problemas.append(f"identificador de valor {l[2]} inválido")
        b.valido = False
        return b
    calc = modulo10 if l[2] in "67" else modulo11_arrecadacao
    blocos = [l[i:i + 12] for i in range(0, 48, 12)]
    for n, bloco in enumerate(blocos, 1):
        if calc(bloco[:11]) != int(bloco[11]):
            b.problemas.append(f"dígito de conferência do {n}º bloco não confere")
    barras = "".join(bl[:11] for bl in blocos)
    if calc(barras[:3] + barras[4:]) != int(barras[3]):
        b.problemas.append("dígito de conferência geral não confere")
    b.valido = not b.problemas
    if l[2] in "68":                    # 6 e 8: valor efetivo em reais
        b.valor = int(barras[4:15]) / 100
    return b


def conferir(texto: str, hoje: date | None = None) -> Boleto | None:
    """Confere uma linha digitavel; None se o texto nao tiver 47 ou 48 digitos."""
    digitos = re.sub(r"\D", "", texto)
    if len(digitos) == 47:
        return _conferir_bancario(digitos, hoje)
    if len(digitos) == 48 and digitos[0] == "8":
        return _conferir_arrecadacao(digitos)
    return None


def encontrar(texto: str, hoje: date | None = None) -> list[Boleto]:
    """Todas as linhas digitaveis presentes num texto (e-mail, SMS, PDF)."""
    achados, vistos = [], set()
    for m in PADRAO_LINHA.finditer(texto or ""):
        b = conferir(m.group(0), hoje)
        if b and b.linha not in vistos:
            vistos.add(b.linha)
            achados.append(b)
    return achados


def montar(banco: str, valor: float, vencimento: date, campo_livre: str) -> str:
    """Monta uma linha digitavel valida (47 digitos). Usado pelos testes e exemplos ficticios."""
    if len(banco) != 3 or len(campo_livre) != 25 or not (banco + campo_livre).isdigit():
        raise ValueError("banco com 3 digitos e campo livre com 25")
    if vencimento >= BASE_NOVA:
        fator = (vencimento - BASE_NOVA).days + 1000
    else:
        fator = (vencimento - BASE_ANTIGA).days
    sem_dv = f"{banco}9{fator:04d}{round(valor * 100):010d}{campo_livre}"
    barras = sem_dv[:4] + str(modulo11_bancario(sem_dv)) + sem_dv[4:]
    c1 = barras[0:4] + barras[19:24]
    c2 = barras[24:34]
    c3 = barras[34:44]
    return f"{c1}{modulo10(c1)}{c2}{modulo10(c2)}{c3}{modulo10(c3)}{barras[4]}{barras[5:19]}"
