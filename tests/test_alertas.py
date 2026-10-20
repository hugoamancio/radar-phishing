"""Alertas. Telegram e Discord sao simulados com httpx.MockTransport: nada sai da maquina."""

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import httpx
import psycopg
import pytest

from alertas import canais, fila
from alertas.__main__ import ciclo
from alertas.config import Config
from alertas.mensagens import Alerta, desarmar
from monitor import banco
from monitor.detector import analisar

CFG = Config(telegram_token="123:SEGREDO", telegram_chat_id="42", discord_webhook="https://discord.com/api/webhooks/1/x",
             nivel_minimo="alto", limite_por_hora=20, janela_horas=2)
AGORA = datetime.now(timezone.utc)


def alerta(titulo="bradesco-app[.]xyz") -> Alerta:
    return Alerta("dominio", 1, titulo, 82, "alto", AGORA, [("Imita", "Bradesco")], ["Marca só no subdomínio"])


def cliente(responder) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(responder))


# --- Texto ------------------------------------------------------------------

@pytest.mark.parametrize("entrada, saida", [
    ("bradesco-app.xyz", "bradesco-app[.]xyz"),
    ("https://login.golpe.top/x", "hxxps://login[.]golpe[.]top/x"),
    ("http://1.2.3.4", "hxxp://1[.]2[.]3[.]4"),
])
def test_endereco_vai_desarmado(entrada, saida):
    assert desarmar(entrada) == saida


def test_telegram_escapa_html_do_dado():
    # Um "dominio" com HTML no nome nao pode virar formatacao (nem link) no Telegram.
    texto = alerta('<a href="x">clique</a>').telegram_html()
    assert '<a href' not in texto and "&lt;a href" in texto


def test_discord_nunca_menciona_todo_mundo():
    corpo = alerta("@everyone golpe[.]top").discord_embed()
    assert corpo["allowed_mentions"] == {"parse": []}
    assert corpo["embeds"][0]["color"] == 0x39FF14


# --- Configuracao ---------------------------------------------------------------

def test_sem_canal_vira_simulacao():
    assert replace(CFG, telegram_token=None, discord_webhook=None).canais == ["simulacao"]
    assert CFG.canais == ["telegram", "discord"]
    assert CFG.niveis_alertados == ("alto", "critico")


def test_webhook_que_nao_e_do_discord_e_recusado():
    # Um endereco qualquer mandaria os dados dos golpes para um servidor desconhecido.
    from alertas import config
    assert config.carregar({"DISCORD_WEBHOOK_URL": "https://servidor-estranho.com/coleta"}).discord_webhook is None
    assert config.carregar({"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/1/abc"}).discord_webhook


def test_le_o_arquivo_env(tmp_path):
    from alertas import config
    (tmp_path / ".env").write_text("# comentario\nTELEGRAM_BOT_TOKEN='abc'\nALERTA_NIVEL_MINIMO=critico\n",
                                   encoding="utf-8")
    env = config.ler_env(tmp_path / ".env")
    assert env["TELEGRAM_BOT_TOKEN"] == "abc"
    assert config.carregar(env).nivel_minimo == "critico"


# --- Envio -----------------------------------------------------------------

def test_telegram_envia_html_sem_preview_de_link():
    recebido = {}

    def responder(req):
        recebido.update(json.loads(req.content))
        return httpx.Response(200, json={"ok": True})

    assert canais.enviar(alerta(), "telegram", CFG, cliente(responder)) is None
    assert recebido["parse_mode"] == "HTML" and recebido["disable_web_page_preview"] is True
    assert recebido["chat_id"] == "42"


def test_limite_do_canal_para_o_ciclo():
    with pytest.raises(canais.LimiteDoCanal):
        canais.enviar(alerta(), "discord", CFG, cliente(lambda req: httpx.Response(429)))


def test_erro_de_rede_nunca_mostra_a_chave_do_bot():
    def cair(req):
        raise httpx.ConnectError("falhou ao conectar em " + str(req.url), request=req)

    erro = canais.enviar(alerta(), "telegram", CFG, cliente(cair))
    assert erro == "ConnectError" and "SEGREDO" not in erro
    erro = canais.enviar(alerta(), "telegram", CFG, cliente(lambda req: httpx.Response(401)))
    assert erro == "HTTP 401"


# --- Fila (com banco, numa transacao desfeita) ---------------------------------------

class _Desfazer(Exception):
    pass


def test_fila_avisa_uma_vez_e_respeita_nivel_e_janela():
    try:
        conn = banco.conectar()
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL fora do ar")
    marcas = banco.carregar_marcas(conn)
    cfg = replace(CFG, telegram_token=None, discord_webhook=None)      # so simulacao
    with pytest.raises(_Desfazer):
        with conn.transaction():
            conn.execute("DELETE FROM alerta WHERE canal = 'simulacao'")
            def detectar(nome, serial, horas_atras=0):
                det = analisar(nome, marcas)[0]
                banco.gravar(conn, det, {"emissor": "Teste", "serial": serial, "log": "t"})
                conn.execute("UPDATE deteccao_dominio SET detectado_em = now() - %s::interval "
                             "WHERE dominio_id = (SELECT id FROM dominio WHERE nome = %s)", (f"{horas_atras} hours", nome))
            detectar("zz.bradesco.support.alerta-teste.xyz", "a1")       # alto, recente: entra
            detectar("bradesco-noticias-teste.com.br", "a2")             # medio: nao entra
            detectar("yy.bradesco.support.antigo-teste.xyz", "a3", 5)    # alto, mas fora da janela

            nomes = [a.titulo for a in fila.pendentes(conn, cfg, "simulacao")]
            assert "zz[.]bradesco[.]support[.]alerta-teste[.]xyz" in nomes
            assert not any("noticias-teste" in n or "antigo-teste" in n for n in nomes)

            assert ciclo(conn, cfg, simular=True) == 0                   # simular nao registra nada
            assert fila.pendentes(conn, cfg, "simulacao")
            ciclo(conn, cfg)                                             # agora "envia" (simulacao)
            assert fila.pendentes(conn, cfg, "simulacao") == []          # ...e nao repete
            raise _Desfazer
    conn.close()
