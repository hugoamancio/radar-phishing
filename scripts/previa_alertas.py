"""Gera docs/imagens/alertas.html (e o PNG, via Edge sem janela): como o alerta aparece
no Telegram e no Discord. O conteudo e o texto EXATO gerado por alertas/mensagens.py,
com dados ficticios; so a "moldura" do aplicativo e imitada.

    python scripts/previa_alertas.py
"""

from __future__ import annotations

import html
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from alertas.mensagens import Alerta, desarmar  # noqa: E402

AGORA = datetime.now(timezone.utc)
ALERTAS = [
    Alerta("dominio", 1, desarmar("x7k2.bradesco.support.entregarapida.click"), 82, "alto", AGORA - timedelta(minutes=3),
           [("Imita", "Bradesco"), ("Certificado", "Let's Encrypt")], ["Marca só no subdomínio", "TLD suspeito"]),
    Alerta("mensagem", 2, "SMS de 11987654321", 90, "critico", AGORA,
           [("Link", desarmar("bradesco-cancelar.top")),
            ("Já conhecido", f"{desarmar('bradesco-cancelar.top')} visto nos CT logs 3 d 2 h antes")],
           ["Link já conhecido como golpe", "Falso alerta de compra", "SMS de banco vindo de celular comum"]),
]

PAGINA = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Alertas</title><style>
body{{margin:0;background:#050a06;font-family:"Segoe UI",system-ui,sans-serif;padding:32px;display:flex;gap:32px;align-items:flex-start}}
.coluna{{width:520px}}
.rotulo{{color:#6fe36a;font:600 12px "Cascadia Code",Consolas,monospace;letter-spacing:.12em;text-transform:uppercase;margin-bottom:10px}}
.tg{{background:#0e1621;border-radius:14px;padding:18px 16px;min-height:520px}}
.tg-topo{{display:flex;align-items:center;gap:10px;color:#fff;font-weight:600;margin:-18px -16px 16px;padding:12px 16px;background:#17212b;border-radius:14px 14px 0 0}}
.av{{width:34px;height:34px;border-radius:50%;background:#050a06;border:2px solid #39ff14;display:grid;place-items:center;color:#39ff14;font:700 14px Consolas}}
.tg-sub{{color:#7f91a4;font-size:12px;font-weight:400}}
.balao{{background:#182533;color:#f5f5f5;border-radius:12px 12px 12px 4px;padding:10px 12px 8px;margin:0 0 12px;max-width:92%;font-size:14.5px;line-height:1.42;white-space:pre-wrap}}
.balao code{{font-family:Consolas,monospace;color:#9fd0ff;font-size:13.5px}}
.balao i{{color:#8da2b5}}
.dc{{background:#313338;border-radius:14px;padding:18px 16px;min-height:520px;color:#dbdee1;font-size:14.5px}}
.dc-msg{{display:flex;gap:12px;margin-bottom:22px}}
.dc-nome{{color:#fff;font-weight:600}} .dc-bot{{background:#5865f2;color:#fff;font-size:10px;border-radius:3px;padding:1px 4px;margin-left:4px;vertical-align:2px}}
.dc-hora{{color:#949ba4;font-size:12px;margin-left:6px}}
.embed{{margin-top:6px;background:#2b2d31;border-left:4px solid #39ff14;border-radius:4px;padding:10px 14px;max-width:440px}}
.embed-t{{color:#fff;font-weight:600;margin-bottom:6px}} .embed code{{font-family:Consolas,monospace;background:#1e1f22;padding:1px 4px;border-radius:3px}}
.campos{{display:grid;grid-template-columns:1fr 1fr;gap:8px 16px;margin-top:8px}} .campo-largo{{grid-column:1/-1}}
.campo b{{display:block;color:#fff;font-size:13px}} .campo span{{white-space:pre-wrap;font-size:13.5px}}
.embed-r{{color:#949ba4;font-size:12px;margin-top:10px}}
</style></head><body>
<div class="coluna"><div class="rotulo">Telegram</div><div class="tg">
<div class="tg-topo"><div class="av">R</div><div>Radar Phishing<div class="tg-sub">bot</div></div></div>
{telegram}</div></div>
<div class="coluna"><div class="rotulo">Discord</div><div class="dc">{discord}</div></div>
</body></html>"""


def discord_html(a: Alerta) -> str:
    emb = a.discord_embed()["embeds"][0]
    e = html.escape
    campos = "".join(
        f'<div class="campo{"" if c["inline"] else " campo-largo"}"><b>{e(c["name"])}</b><span>{e(c["value"])}</span></div>'
        for c in emb["fields"])
    descricao = e(emb["description"]).replace("`" + e(a.titulo) + "`", f"<code>{e(a.titulo)}</code>")
    return (f'<div class="dc-msg"><div class="av">R</div><div><span class="dc-nome">Radar Phishing</span>'
            f'<span class="dc-bot">APP</span><span class="dc-hora">hoje às {a.quando.astimezone():%H:%M}</span>'
            f'<div class="embed"><div class="embed-t">{e(emb["title"])}</div><div>{descricao.replace(chr(10), "<br>")}</div>'
            f'<div class="campos">{campos}</div><div class="embed-r">{e(emb["footer"]["text"])}</div></div></div></div>')


def main() -> None:
    # telegram_html ja escapa todo dado; aqui ele entra como o Telegram o mostraria.
    pagina = PAGINA.format(telegram="".join(f'<div class="balao">{a.telegram_html()}</div>' for a in ALERTAS),
                           discord="".join(discord_html(a) for a in ALERTAS))
    destino_html = RAIZ / "docs" / "imagens" / "alertas.html"
    destino_html.write_text(pagina, encoding="utf-8")
    destino_png = RAIZ / "docs" / "imagens" / "alertas.png"
    edge = next((p for p in (Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
                             Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")) if p.exists()), None)
    if edge:
        with tempfile.TemporaryDirectory() as perfil:
            subprocess.run([str(edge), "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={perfil}",
                            "--window-size=1150,820", f"--screenshot={destino_png}", destino_html.as_uri()],
                           check=False, capture_output=True, timeout=60)
    print(destino_html, destino_png if destino_png.exists() else "(sem Edge: abra o HTML)")


if __name__ == "__main__":
    main()
