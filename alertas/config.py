"""Configuracao dos alertas, lida do arquivo .env (que nunca vai para o Git).

Sem nenhum canal configurado, os alertas rodam em modo simulacao: mostram na
tela exatamente o que seria enviado, e nada sai do computador.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from monitor import configuracao

RAIZ = Path(__file__).resolve().parent.parent
NIVEIS = ("baixo", "medio", "alto", "critico")


def ler_env(caminho: Path = RAIZ / ".env") -> dict[str, str]:
    """O .env, mais as variaveis de ambiente dos alertas (que tem prioridade)."""
    return configuracao.ler_env(caminho, prefixos=("TELEGRAM_", "DISCORD_", "ALERTA_"))


@dataclass(frozen=True)
class Config:
    telegram_token: str | None
    telegram_chat_id: str | None
    discord_webhook: str | None
    nivel_minimo: str           # so avisa deste nivel para cima
    limite_por_hora: int        # trava contra enxurrada de alertas
    janela_horas: int           # so avisa o que apareceu nas ultimas N horas

    @property
    def canais(self) -> list[str]:
        canais = []
        if self.telegram_token and self.telegram_chat_id:
            canais.append("telegram")
        if self.discord_webhook:
            canais.append("discord")
        return canais or ["simulacao"]

    @property
    def niveis_alertados(self) -> tuple[str, ...]:
        return NIVEIS[NIVEIS.index(self.nivel_minimo):]


def carregar(env: dict[str, str] | None = None) -> Config:
    """``env`` permite passar os valores direto (testes); sem ele, le o .env."""
    env = ler_env() if env is None else env
    nivel = env.get("ALERTA_NIVEL_MINIMO", "alto").lower()
    if nivel not in NIVEIS:
        nivel = "alto"
    webhook = env.get("DISCORD_WEBHOOK_URL") or None
    # So aceita webhook do proprio Discord: um endereco qualquer aqui mandaria os
    # dados dos golpes detectados para um servidor desconhecido.
    if webhook and not webhook.startswith(("https://discord.com/api/webhooks/", "https://discordapp.com/api/webhooks/")):
        webhook = None
    return Config(
        telegram_token=env.get("TELEGRAM_BOT_TOKEN") or None,
        telegram_chat_id=env.get("TELEGRAM_CHAT_ID") or None,
        discord_webhook=webhook,
        nivel_minimo=nivel,
        limite_por_hora=int(env.get("ALERTA_LIMITE_POR_HORA", "20")),
        janela_horas=int(env.get("ALERTA_JANELA_HORAS", "2")),
    )
