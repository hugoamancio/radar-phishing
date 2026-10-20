"""Leitura do arquivo .env, compartilhada pelo sistema todo.

Segredos (senha do banco, token do bot) ficam so no .env, que nunca vai para
o Git. Variaveis de ambiente de mesmo nome tem prioridade sobre o arquivo.
"""

from __future__ import annotations

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def ler_env(caminho: Path = RAIZ / ".env", prefixos: tuple[str, ...] = ()) -> dict[str, str]:
    """CHAVE=valor por linha; # comenta. ``prefixos`` limita quais variaveis de ambiente entram."""
    valores: dict[str, str] = {}
    if caminho.is_file():
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            valores[chave.strip()] = valor.strip().strip('"').strip("'")
    for chave, valor in os.environ.items():
        if not prefixos or chave.startswith(prefixos):
            if chave in valores or prefixos:
                valores[chave] = valor
    return valores
