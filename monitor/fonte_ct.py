"""Recebe os certificados novos do servidor CertStream local (ver docker-compose.yml)."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator, Callable

import websockets

URL_PADRAO = os.environ.get("RADAR_CERTSTREAM", "ws://localhost:8080/")


async def certificados(ao_mudar_status: Callable[[str], None]) -> AsyncIterator[dict]:
    """Gera um dicionario simples por certificado, reconectando sozinho se cair.

    A espera entre tentativas dobra a cada falha (1 s, 2 s, 4 s... ate 30 s)
    para nao martelar um servidor que esta reiniciando.
    """
    espera = 1
    while True:
        try:
            ao_mudar_status("conectando")
            # Sem ping de keepalive: a resposta (pong) chega na fila atras de milhares
            # de certificados e estoura o prazo, derrubando uma conexao saudavel.
            # Num fluxo continuo, o proprio dado chegando prova que a conexao vive;
            # se ele parar, o servidor fecha o socket e o laco abaixo reconecta.
            async with websockets.connect(URL_PADRAO, open_timeout=10, max_size=2**23,
                                          ping_interval=None, ping_timeout=None) as ws:
                ao_mudar_status("conectado")
                espera = 1
                async for bruto in ws:
                    msg = json.loads(bruto)
                    if msg.get("message_type") != "certificate_update":
                        continue
                    dados = msg["data"]
                    folha = dados.get("leaf_cert", {})
                    yield {
                        "dominios": folha.get("all_domains") or [],
                        "emissor": (folha.get("issuer") or {}).get("O"),
                        "emitido_em": folha.get("not_before"),
                        "serial": folha.get("serial_number"),
                        "log": (dados.get("source") or {}).get("name"),
                    }
        except (OSError, websockets.WebSocketException, asyncio.TimeoutError):
            ao_mudar_status(f"reconectando em {espera} s")
            await asyncio.sleep(espera)
            espera = min(espera * 2, 30)
