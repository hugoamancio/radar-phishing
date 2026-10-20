"""Gera docs/imagens/cruzamento.svg com dados FICTICIOS, dentro de uma transacao desfeita.

    python scripts/previa_cruzamento.py

Precisa do banco no ar. Nada fica gravado: tudo e inserido, desenhado e desfeito.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from rich.console import Console  # noqa: E402

from cruzamento.consulta import ler, resumir  # noqa: E402
from cruzamento.tela import TelaCruzamento  # noqa: E402
from monitor import banco  # noqa: E402
from monitor.detector import analisar  # noqa: E402
from risco.banco import gravar  # noqa: E402
from risco.modelo import calcular  # noqa: E402

AGORA = datetime.now(timezone.utc)
# (dominio, horas entre o CT e a chegada; None = nunca visto, negativo = CT depois, canal)
CASOS = [
    ("bradesco-cancelar.top", 74, "sms"),
    ("x7k2.bradesco.support.entregarapida.click", 31, "e-mail"),
    ("bradesco-pix-seguro.xyz", 6.5, "whatsapp"),
    ("atualizacao-bradesco.online", -2, "e-mail"),
    ("bardesco-token.top", None, "sms"),
]


class _Desfazer(Exception):
    pass


def main() -> None:
    conn = banco.conectar()
    marcas = banco.carregar_marcas(conn)
    try:
        with conn.transaction():
            for i, (nome, horas, canal) in enumerate(CASOS):
                chegada = AGORA - timedelta(hours=10 * i + 2)
                dominio_id = conn.execute("INSERT INTO dominio (nome, marca_id) VALUES (%s, 1) RETURNING id",
                                          (nome,)).fetchone()[0]
                gravar(conn, calcular(analisar(nome, marcas)[0].tecnicas), dominio_id=dominio_id)
                if horas is not None:
                    conn.execute("INSERT INTO certificado (dominio_id, fonte, serial, visto_em) "
                                 "VALUES (%s, 'previa', %s, %s)", (dominio_id, f"p{i}", chegada - timedelta(hours=horas)))
                if canal == "e-mail":
                    origem = conn.execute("INSERT INTO email (remetente, recebido_em, arquivo_sha256) "
                                          "VALUES ('aviso@golpe.top', %s, %s) RETURNING id",
                                          (chegada, f"previa{i}")).fetchone()[0]
                    conn.execute("INSERT INTO link_email (email_id, dominio_id, url) VALUES (%s, %s, 'x')",
                                 (origem, dominio_id))
                else:
                    origem = conn.execute("INSERT INTO mensagem (texto_sha256, canal, analisada_em) "
                                          "VALUES (%s, %s, %s) RETURNING id", (f"previa{i}", canal, chegada)).fetchone()[0]
                    conn.execute("INSERT INTO link_mensagem (mensagem_id, dominio_id, url) VALUES (%s, %s, 'x')",
                                 (origem, dominio_id))
            itens = [c for c in ler(conn) if c.dominio in {n for n, _, _ in CASOS}]
            for nome, largura in (("cruzamento", 150), ("cruzamento-estreito", 90)):
                console = Console(record=True, width=largura, force_terminal=True, color_system="truecolor")
                console.print(TelaCruzamento(itens, resumir(itens)))
                destino = RAIZ / "docs" / "imagens" / f"{nome}.svg"
                console.save_svg(str(destino), title="Radar Phishing — cruzamento")
                print(destino)
            raise _Desfazer
    except _Desfazer:
        pass


if __name__ == "__main__":
    main()
