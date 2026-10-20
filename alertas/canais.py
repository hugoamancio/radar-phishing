"""Envio para Telegram e Discord.

Cuidado com a chave: no Telegram ela faz parte do endereco
(api.telegram.org/bot<CHAVE>/...), e as excecoes do httpx trazem o endereco
completo na mensagem. Por isso nenhum erro e repassado como veio: so o tipo
do problema e o codigo HTTP, nunca a URL.
"""

from __future__ import annotations

import httpx

from alertas.config import Config
from alertas.mensagens import Alerta

TIMEOUT = httpx.Timeout(10.0)


class LimiteDoCanal(Exception):
    """O canal pediu para esperar (HTTP 429). O ciclo para e tenta de novo depois."""


def _erro_seguro(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return type(exc).__name__        # ConnectTimeout, ConnectError... sem a URL


def telegram(a: Alerta, cfg: Config, cliente: httpx.Client) -> None:
    r = cliente.post(f"https://api.telegram.org/bot{cfg.telegram_token}/sendMessage", json={
        "chat_id": cfg.telegram_chat_id, "text": a.telegram_html(), "parse_mode": "HTML",
        "disable_web_page_preview": True,
    })
    if r.status_code == 429:
        raise LimiteDoCanal()
    r.raise_for_status()
    if not r.json().get("ok"):
        raise ValueError("Telegram recusou a mensagem")


def discord(a: Alerta, cfg: Config, cliente: httpx.Client) -> None:
    r = cliente.post(cfg.discord_webhook, params={"wait": "true"}, json=a.discord_embed())
    if r.status_code == 429:
        raise LimiteDoCanal()
    r.raise_for_status()


ENVIOS = {"telegram": telegram, "discord": discord}


def enviar(a: Alerta, canal: str, cfg: Config, cliente: httpx.Client | None = None) -> str | None:
    """Envia; devolve None se deu certo ou o motivo da falha (sem dados sensiveis)."""
    if canal == "simulacao":
        return None
    proprio = cliente is None
    cliente = cliente or httpx.Client(timeout=TIMEOUT)
    try:
        ENVIOS[canal](a, cfg, cliente)
        return None
    except LimiteDoCanal:
        raise
    except Exception as exc:          # noqa: BLE001 - qualquer falha vira registro, nunca derruba o laco
        return _erro_seguro(exc)
    finally:
        if proprio:
            cliente.close()
