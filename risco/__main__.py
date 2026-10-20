"""Motor de risco.

    python -m risco pesos        tabela de pesos do modelo, por familia
    python -m risco reavaliar    reaplica detector e modelo atuais a tudo que esta no banco
"""

from __future__ import annotations

import argparse
import json

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from monitor import banco
from monitor.detector import analisar
from monitor.painel import COR_BORDA, COR_ROTULO
from risco.banco import gravar
from risco.modelo import FATOR_REPETICAO, NOTA_MAXIMA, PESOS, VERSAO, calcular, nivel_da_nota
from risco.visual import mini

console = Console()

NOMES_FAMILIAS = {
    "imitacao": "Domínio · imitação da marca", "isca": "Domínio · palavras de golpe", "tld": "Domínio · terminação",
    "identidade": "E-mail e SMS · remetente", "autenticacao": "E-mail · autenticação",
    "links": "E-mail e SMS · links",
    "linguagem": "E-mail e SMS · linguagem", "anexos": "E-mail · anexos",
    "boleto": "Boleto", "pix": "Pix",
}


def mostrar_pesos() -> None:
    # Familia como titulo e sinais embaixo: cabe ate num terminal de 45 colunas
    # (a versao em colunas lado a lado cortava tudo no terminal estreito do app).
    console.print(Text(f"Pesos do modelo {VERSAO}", style="bold white"))
    console.print(Text("Quanto cada sinal, sozinho, indica golpe (0 a 100).\n", style=COR_ROTULO))
    grade = Table.grid(padding=(0, 2))
    grade.add_column(no_wrap=True, overflow="ellipsis")
    grade.add_column(no_wrap=True)
    for familia, titulo in NOMES_FAMILIAS.items():
        grade.add_row(Text(titulo, style=COR_ROTULO), "")
        itens = sorted((p for p in PESOS.values() if p[1] == familia), key=lambda p: -p[0])
        for peso, _, nome in itens:
            grade.add_row(Text(f"  {nome}", style="white"), mini(peso, nivel_da_nota(peso)))
        grade.add_row("", "")
    console.print(grade)
    console.print(Text(
        f"Sinais se combinam como chances independentes: nota = 100 × (1 − Π(1 − peso/100)).\n"
        f"A partir do segundo sinal da mesma família, o peso vale {FATOR_REPETICAO:.0%}. "
        f"Nota máxima exibida: {NOTA_MAXIMA}.", style=COR_ROTULO))


def reavaliar() -> None:
    conn = banco.conectar()
    marcas = {m.id: m for m in banco.carregar_marcas(conn)}
    tabela = Table(box=box.SIMPLE_HEAD, header_style=COR_ROTULO, border_style=COR_BORDA, expand=True)
    tabela.add_column("Item", overflow="fold", ratio=3)
    tabela.add_column("Antes", no_wrap=True)
    tabela.add_column("Depois", no_wrap=True)
    tabela.add_column("O que mudou", style=COR_ROTULO, ratio=2)
    removidos = atualizados = 0

    deteccoes = conn.execute(
        "SELECT dd.id, d.id, d.nome, dd.marca_id, dd.tecnicas, r.nota, r.nivel "
        "FROM deteccao_dominio dd JOIN dominio d ON d.id = dd.dominio_id "
        "LEFT JOIN vw_risco_atual r ON r.dominio_id = d.id AND r.email_id IS NULL ORDER BY d.nome"
    ).fetchall()
    for det_id, dominio_id, nome, marca_id, tecnicas_antes, nota_antes, nivel_antes in deteccoes:
        antes = mini(nota_antes, nivel_antes) if nota_antes is not None else Text("—", style=COR_BORDA)
        atual = next((d for d in analisar(nome, [marcas[marca_id]])), None)
        with conn.transaction():
            if atual is None:
                # A deteccao some; dominio e certificados ficam (sao fatos, nao opiniao).
                conn.execute("DELETE FROM deteccao_dominio WHERE id = %s", (det_id,))
                gravar(conn, calcular([]), dominio_id=dominio_id)
                removidos += 1
                tabela.add_row(nome, antes, Text("removido", style="bold white"),
                               "o detector atual não considera mais suspeito (falso positivo)")
                continue
            conn.execute(
                "UPDATE deteccao_dominio SET tecnicas = %s, motivos = %s, trecho = %s, atualizado_em = now() "
                "WHERE id = %s",
                (atual.tecnicas, json.dumps(atual.motivos, ensure_ascii=False), atual.trecho, det_id))
            a = calcular(atual.tecnicas)
            if gravar(conn, a, dominio_id=dominio_id):
                atualizados += 1
                novas = sorted(set(atual.tecnicas) - set(tecnicas_antes))
                tabela.add_row(nome, antes, mini(a.nota, a.nivel),
                               ("nova técnica: " + ", ".join(PESOS[t][2] for t in novas)) if novas else "pesos do modelo atual")

    for email_id, remetente, achados, nota_antes, nivel_antes in conn.execute(
        "SELECT e.id, e.remetente, e.achados, r.nota, r.nivel FROM email e "
        "LEFT JOIN vw_risco_atual r ON r.email_id = e.id AND r.dominio_id IS NULL"
    ).fetchall():
        a = calcular([x["tecnica"] for x in achados])
        with conn.transaction():
            if gravar(conn, a, email_id=email_id):
                atualizados += 1
                antes = mini(nota_antes, nivel_antes) if nota_antes is not None else Text("—", style=COR_BORDA)
                tabela.add_row(f"e-mail de {remetente}", antes, mini(a.nota, a.nivel), "pesos do modelo atual")

    for mensagem_id, canal, achados, nota_antes, nivel_antes in conn.execute(
        "SELECT ms.id, ms.canal, ms.achados, r.nota, r.nivel FROM mensagem ms "
        "LEFT JOIN vw_risco_atual r ON r.mensagem_id = ms.id"
    ).fetchall():
        a = calcular([x["tecnica"] for x in achados])
        with conn.transaction():
            if gravar(conn, a, mensagem_id=mensagem_id):
                atualizados += 1
                antes = mini(nota_antes, nivel_antes) if nota_antes is not None else Text("—", style=COR_BORDA)
                tabela.add_row(f"{canal} nº {mensagem_id}", antes, mini(a.nota, a.nivel), "pesos do modelo atual")

    if tabela.row_count:
        console.print(tabela)
    console.print(Text(f"{len(deteccoes)} domínios revistos  ·  {atualizados} notas novas  ·  "
                       f"{removidos} falsos positivos removidos  ·  modelo {VERSAO}", style=COR_ROTULO))


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m risco", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("pesos", help="mostra a tabela de pesos")
    sub.add_parser("reavaliar", help="recalcula tudo que está no banco")
    args = parser.parse_args()
    {"pesos": mostrar_pesos, "reavaliar": reavaliar}[args.comando]()


if __name__ == "__main__":
    main()
