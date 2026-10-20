"""Texto dos alertas.

Regra de seguranca: todo endereco de golpe vai "desarmado" (hxxps://, [.]),
a notacao de analistas para link que nao vira clicavel. Um alerta nao pode
ser o caminho para alguem cair no proprio golpe que ele avisa.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime

from risco.modelo import NOMES_NIVEIS

NOMES_TIPO = {"dominio": "Domínio suspeito nos CT logs", "email": "E-mail de golpe", "mensagem": "Mensagem de golpe"}
NOMES_CANAL = {"e-mail": "E-mail", "sms": "SMS", "whatsapp": "WhatsApp", "outro": "Mensagem"}


def desarmar(endereco: str) -> str:
    """bradesco-app.xyz -> bradesco-app[.]xyz ; https://x.top -> hxxps://x[.]top"""
    texto = endereco.replace("https://", "hxxps://").replace("http://", "hxxp://")
    return texto.replace(".", "[.]")


def barra(nota: int) -> str:
    # Blocos simples: "▰▱" viravam quadradinhos vazados em fontes sem esses simbolos.
    cheios = round(nota / 10)
    return "█" * cheios + "░" * (10 - cheios)


@dataclass
class Alerta:
    tipo: str                    # dominio, email, mensagem
    alvo_id: int
    titulo: str                  # o dominio, o remetente...
    nota: int
    nivel: str
    quando: datetime
    detalhes: list[tuple[str, str]] = field(default_factory=list)   # (rotulo, valor), ja desarmados
    motivos: list[str] = field(default_factory=list)

    def texto_simples(self) -> str:
        linhas = [f"RADAR PHISHING · {NOMES_TIPO[self.tipo]}",
                  f"{self.titulo}",
                  f"Risco {self.nota} · {NOMES_NIVEIS[self.nivel]}  {barra(self.nota)}"]
        linhas += [f"{r}: {v}" for r, v in self.detalhes]
        if self.motivos:
            linhas.append("Por quê: " + "; ".join(self.motivos))
        linhas.append(f"{self.quando.astimezone():%d/%m/%Y %H:%M}")
        return "\n".join(linhas)

    def telegram_html(self) -> str:
        """HTML aceito pelo Telegram (b, i, code). Todo dado passa por html.escape."""
        e = html.escape
        partes = [f"<b>RADAR PHISHING · {e(NOMES_NIVEIS[self.nivel].upper())}</b>",
                  e(NOMES_TIPO[self.tipo]),
                  f"<code>{e(self.titulo)}</code>",
                  f"<b>Risco {self.nota}</b> · {e(NOMES_NIVEIS[self.nivel])}  {barra(self.nota)}", ""]
        partes += [f"<b>{e(r)}:</b> {e(v)}" for r, v in self.detalhes]
        if self.motivos:
            partes += ["", "<b>Por quê</b>"] + [f"• {e(m)}" for m in self.motivos]
        partes += ["", f"<i>{self.quando.astimezone():%d/%m/%Y %H:%M} · endereços desarmados: não clique</i>"]
        return "\n".join(partes)

    def discord_embed(self) -> dict:
        campos = [{"name": r, "value": v[:1024], "inline": len(v) < 30} for r, v in self.detalhes]
        if self.motivos:
            campos.append({"name": "Por quê", "value": "\n".join(f"• {m}" for m in self.motivos)[:1024], "inline": False})
        return {
            "username": "Radar Phishing",
            "allowed_mentions": {"parse": []},       # nunca @everyone, mesmo que um dado traga o texto
            "embeds": [{
                "title": f"{NOMES_TIPO[self.tipo]} · risco {self.nota} ({NOMES_NIVEIS[self.nivel]})",
                "description": f"`{self.titulo}`\n{barra(self.nota)}",
                "color": 0x39FF14,
                "fields": campos,
                "footer": {"text": "Endereços desarmados: não clique"},
                "timestamp": self.quando.isoformat(),
            }],
        }
