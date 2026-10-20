"""Monta o relatorio de inteligencia como uma pagina HTML unica.

Arquivo autocontido (CSS embutido, sem script, sem nada da internet): abre em
qualquer navegador e pode ser enviado por e-mail. Ao imprimir ou salvar em PDF,
troca o tema neon por preto no branco. Todo dado passa por html.escape.
"""

from __future__ import annotations

from collections import Counter
from html import escape as e

from alertas.mensagens import desarmar
from cruzamento.consulta import duracao
from monitor.detector import NOMES_TECNICAS
from relatorio import iocs
from relatorio.coleta import Dados
from risco.modelo import NOMES_NIVEIS, PESOS

COR_NIVEL = {"baixo": "#1a6b2a", "medio": "#26a33a", "alto": "#2fd94a", "critico": "#39ff14"}

CSS = """
:root{--fundo:#050a06;--painel:#08110a;--borda:#15301b;--borda2:#1f4a28;--texto:#b9ffb0;--texto2:#6fe36a;
--texto3:#3f9e45;--neon:#39ff14;--brilho:0 0 6px rgba(57,255,20,.5),0 0 18px rgba(57,255,20,.2)}
*{box-sizing:border-box}html,body{margin:0}
body{background:var(--fundo);color:var(--texto);font:14px/1.55 "Cascadia Code",Consolas,"Courier New",monospace;
font-variant-numeric:tabular-nums}
main{max-width:1080px;margin:0 auto;padding:40px 28px 60px}
h1{font-size:26px;color:var(--neon);text-shadow:var(--brilho);margin:0;letter-spacing:.04em}
h1 span{color:var(--texto3);text-shadow:none}
h2{font-size:15px;color:var(--neon);margin:42px 0 6px;letter-spacing:.06em;text-transform:uppercase}
h2 small{display:block;color:var(--texto3);font-size:12px;text-transform:none;letter-spacing:0;font-weight:400;margin-top:2px}
h3{font-size:14px;color:var(--texto);margin:0 0 6px}
p{margin:6px 0}.apagado{color:var(--texto3)}.sec{color:var(--texto2)}
.capa{border-bottom:1px solid var(--borda2);padding-bottom:18px}
.meta{color:var(--texto2);margin-top:6px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:22px}
.kpi{background:var(--painel);border:1px solid var(--borda);border-radius:10px;padding:14px 16px}
.kpi b{display:block;font-size:30px;color:var(--neon);text-shadow:var(--brilho);line-height:1.15}
.kpi span{color:var(--texto3);font-size:11px;letter-spacing:.1em;text-transform:uppercase}
.kpi small{display:block;color:var(--texto2);font-size:12px}
.destaque{background:var(--painel);border:1px solid var(--borda2);border-left:4px solid var(--neon);border-radius:8px;
padding:14px 16px;margin-top:16px}
.destaque ul{margin:6px 0 0;padding-left:18px}.destaque li{margin:4px 0}
.campanha{background:var(--painel);border:1px solid var(--borda);border-radius:10px;padding:16px;margin-top:14px}
.campanha-topo{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:baseline}
.molde{color:var(--neon);font-size:16px;font-weight:700;text-shadow:var(--brilho)}
.fatos{display:grid;grid-template-columns:max-content 1fr;gap:3px 18px;margin-top:10px}
.fatos dt{color:var(--texto3)}.fatos dd{margin:0;word-break:break-all}
.hosts{margin:10px 0 0;padding:10px 12px;background:var(--fundo);border:1px solid var(--borda);border-radius:6px;
color:var(--texto2);font-size:12.5px;word-break:break-all}
table{width:100%;border-collapse:collapse;margin-top:10px}
th{text-align:left;color:var(--texto3);font-size:11px;letter-spacing:.1em;text-transform:uppercase;font-weight:600;
padding:0 10px 6px 0;border-bottom:1px solid var(--borda2)}
td{padding:7px 10px 7px 0;border-bottom:1px solid var(--borda);vertical-align:top}
td.num{text-align:right;white-space:nowrap}td.dom{word-break:break-all}
.barra{height:8px;border-radius:4px;background:#12291a;overflow:hidden;min-width:120px}
.barra i{display:block;height:100%;border-radius:4px;background:var(--neon);box-shadow:0 0 8px rgba(57,255,20,.45)}
.duas{display:grid;grid-template-columns:1fr 1fr;gap:22px}
.horas{display:grid;grid-template-columns:repeat(24,1fr);gap:3px;align-items:end;height:110px;margin-top:12px}
.horas div{background:var(--neon);border-radius:3px 3px 0 0;box-shadow:0 0 6px rgba(57,255,20,.4);min-height:2px}
.horas div.zero{background:#12291a;box-shadow:none}
.horas-eixo{display:grid;grid-template-columns:repeat(24,1fr);gap:3px;color:var(--texto3);font-size:10px;text-align:center}
.selo{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:700;color:#050a06}
.vazio{color:var(--texto3);padding:10px 0}
footer{margin-top:48px;border-top:1px solid var(--borda2);padding-top:14px;color:var(--texto3);font-size:12px}
@media (max-width:760px){.kpis{grid-template-columns:1fr 1fr}.duas{grid-template-columns:1fr}}
@media print{
 :root{--fundo:#fff;--painel:#fff;--borda:#ccc;--borda2:#999;--texto:#000;--texto2:#222;--texto3:#555;--neon:#0a5c1a;--brilho:none}
 body{font-size:11px}main{padding:0;max-width:none}.kpi b,.molde,h1{text-shadow:none}
 .barra i,.horas div{box-shadow:none}.campanha,.destaque,table{break-inside:avoid}
}
"""


def _pct(n: int, total: int) -> str:
    return f"{round(n / total * 100)}%" if total else "—"


def _tabela_contagem(contagem: Counter, nomes: dict[str, str] | None = None, limite: int = 8) -> str:
    if not contagem:
        return '<p class="vazio">Nada no período.</p>'
    total = sum(contagem.values())
    maior = max(contagem.values())
    linhas = "".join(
        f'<tr><td>{e((nomes or {}).get(k, k))}</td><td class="num">{v}</td><td class="num apagado">{_pct(v, total)}</td>'
        f'<td><div class="barra"><i style="width:{max(3, round(v / maior * 100))}%"></i></div></td></tr>'
        for k, v in contagem.most_common(limite))
    return f'<table><tr><th>Item</th><th class="num">Qtd.</th><th class="num">%</th><th></th></tr>{linhas}</table>'


def _selo(nivel: str, nota: int) -> str:
    return f'<span class="selo" style="background:{COR_NIVEL[nivel]}">{nota} · {e(NOMES_NIVEIS[nivel])}</span>'


def _achados_principais(dados: Dados) -> list[str]:
    """Frases do resumo executivo, calculadas dos dados (nada escrito a mao)."""
    frases = []
    campanhas = [c for c in dados.campanhas if c.por_molde and len(c.dominios_registrados) > 1]
    if campanhas:
        c = campanhas[0]
        frases.append(f'A campanha com molde <b>{e(c.chave)}</b> usou {len(c.dominios_registrados)} domínios '
                      f'registrados diferentes e {len(c.enderecos)} endereços: o golpista troca o domínio, mas mantém o molde.')
    if dados.por_tecnica:
        tecnica, n = dados.por_tecnica.most_common(1)[0]
        frases.append(f'A técnica mais usada foi <b>{e(NOMES_TECNICAS.get(tecnica, tecnica))}</b> '
                      f'({n} de {len(dados.deteccoes)} domínios).')
    if dados.por_emissor:
        emissor, n = dados.por_emissor.most_common(1)[0]
        frases.append(f'{_pct(n, len(dados.deteccoes))} dos certificados foram emitidos por <b>{e(emissor)}</b>, '
                      'que emite de graça e em segundos: o cadeado não diz nada sobre a honestidade do site.')
    graves = dados.por_nivel["alto"] + dados.por_nivel["critico"]
    if dados.deteccoes:
        frases.append(f'{graves} de {len(dados.deteccoes)} domínios ({_pct(graves, len(dados.deteccoes))}) '
                      'ficaram com risco alto ou crítico.')
    c = dados.cruzamento
    if c and c.total:
        frases.append(f'Dos golpes que chegaram por e-mail ou mensagem, {_pct(c.antes, c.total)} já eram conhecidos '
                      f'nos CT logs antes de chegar (mediana de {e(duracao(c.mediana))} de antecedência).')
    return frases


def montar(dados: Dados) -> str:
    total = len(dados.deteccoes)
    graves = dados.por_nivel["alto"] + dados.por_nivel["critico"]
    campanhas = [c for c in dados.campanhas if c.e_campanha]
    recebidos = sum(dados.recebidos.values())
    c = dados.cruzamento
    periodo = f"{dados.inicio.astimezone():%d/%m/%Y %H:%M} a {dados.fim.astimezone():%d/%m/%Y %H:%M}"

    partes = [f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Radar Phishing · relatório</title>
<style>{CSS}</style></head><body><main>
<header class="capa"><h1>Radar<span>//</span>Phishing · relatório de inteligência</h1>
<p class="meta">Período: {e(periodo)} · Marcas: {e(", ".join(dados.marcas))}</p>
<p class="apagado">Fontes: CT logs (públicos), e-mails e mensagens próprios ou autorizados. Endereços de golpe
aparecem como texto, nunca como link; na lista de indicadores, desarmados ([.]).</p></header>
<section class="kpis">
<div class="kpi"><span>Domínios suspeitos</span><b>{total}</b><small>{graves} com risco alto ou crítico</small></div>
<div class="kpi"><span>Campanhas</span><b>{len(campanhas)}</b><small>grupos com mais de um endereço</small></div>
<div class="kpi"><span>Golpes recebidos</span><b>{dados.recebidos_golpe}</b><small>de {recebidos} e-mails e mensagens</small></div>
<div class="kpi"><span>Conhecidos antes</span><b>{_pct(c.antes, c.total) if c else "—"}</b>
<small>{f"mediana {e(duracao(c.mediana))} antes" if c and c.total else "nenhum golpe recebido"}</small></div>
</section>"""]

    frases = _achados_principais(dados)
    partes.append('<h2>Resumo executivo<small>Calculado dos dados do período</small></h2><div class="destaque">'
                  + ("<ul>" + "".join(f"<li>{f}</li>" for f in frases) + "</ul>" if frases
                     else '<p class="vazio">Sem detecções no período.</p>') + "</div>")

    partes.append('<h2>Campanhas<small>Domínios agrupados pelo molde do golpista (parte fixa do endereço) '
                  'ou pelo domínio registrado</small></h2>')
    if not campanhas:
        partes.append('<p class="vazio">Nenhum grupo com mais de um endereço no período.</p>')
    for camp in campanhas:
        tlds = ", ".join(f".{t}" for t in camp.tlds)
        emissores = ", ".join(f"{k} ({v})" for k, v in camp.emissores.most_common())
        tipo = "molde no subdomínio" if camp.por_molde else "mesmo domínio registrado"
        janela = f"{camp.primeira.astimezone():%d/%m %H:%M} a {camp.ultima.astimezone():%d/%m %H:%M}"
        partes.append(f"""<div class="campanha"><div class="campanha-topo"><span class="molde">{e(camp.chave)}</span>
{_selo(max(camp.deteccoes, key=lambda d: d.nota).nivel, camp.nota_maxima)}</div>
<dl class="fatos"><dt>Agrupado por</dt><dd>{tipo}</dd><dt>Endereços</dt><dd>{len(camp.enderecos)} (com e sem www: {len(camp.hosts)})</dd>
<dt>Domínios registrados</dt><dd>{e(", ".join(camp.dominios_registrados))}</dd><dt>Terminações</dt><dd>{e(tlds)}</dd>
<dt>Certificados</dt><dd>{e(emissores)}</dd><dt>Atividade</dt><dd>{e(janela)}</dd></dl>
<div class="hosts">{"<br>".join(e(h) for h in camp.hosts)}</div></div>""")

    nomes_tec = {t: NOMES_TECNICAS.get(t, t) for t in dados.por_tecnica}
    partes.append(f"""<h2>Técnicas e infraestrutura<small>O que os golpistas usaram para imitar a marca e
onde hospedaram</small></h2><div class="duas"><div><h3>Técnica principal</h3>{_tabela_contagem(dados.por_tecnica, nomes_tec)}</div>
<div><h3>Nível de risco</h3>{_tabela_contagem(Counter({NOMES_NIVEIS[n]: dados.por_nivel[n] for n in ("critico", "alto", "medio", "baixo") if dados.por_nivel[n]}))}</div>
<div><h3>Terminação (TLD)</h3>{_tabela_contagem(Counter({"." + k: v for k, v in dados.por_tld.items()}))}</div>
<div><h3>Emissor do certificado</h3>{_tabela_contagem(dados.por_emissor)}</div></div>""")

    horas = dados.por_hora
    maior = max(horas) or 1
    barras = "".join(f'<div class="{"zero" if h == 0 else ""}" style="height:{max(2, round(h / maior * 100))}%" '
                     f'title="{i:02d}h: {h}"></div>' for i, h in enumerate(horas))
    eixo = "".join(f"<span>{i:02d}</span>" if i % 3 == 0 else "<span></span>" for i in range(24))
    partes.append(f'<h2>Horário das detecções<small>Hora local em que o certificado apareceu nos CT logs</small></h2>'
                  f'<div class="horas">{barras}</div><div class="horas-eixo">{eixo}</div>')

    nomes_rec = {t: PESOS.get(t, (0, "", t))[2] for t in dados.achados_recebidos}
    partes.append(f"""<h2>E-mails e mensagens<small>Sinais mais frequentes no que foi analisado</small></h2>
<p class="sec">{" · ".join(f"{e(k)}: {v}" for k, v in dados.recebidos.items()) or "Nada analisado no período."}</p>
{_tabela_contagem(dados.achados_recebidos, nomes_rec) if dados.achados_recebidos else ""}""")

    linhas_ioc = iocs.linhas(dados)
    corpo_ioc = "".join(
        f'<tr><td class="dom">{e(l["desarmado"])}</td><td class="num">{l["nota"]}</td><td>{e(l["tecnica"])}</td>'
        f'<td>{e(l["campanha"]) or "—"}</td></tr>' for l in linhas_ioc)
    partes.append(f"""<h2>Indicadores (IOCs)<small>Domínios de risco médio para cima, desarmados. Também exportados
em CSV e em STIX 2.1, para importar em SIEM ou MISP</small></h2>
{f'<table><tr><th>Domínio</th><th class="num">Nota</th><th>Técnica</th><th>Campanha</th></tr>{corpo_ioc}</table>'
 if linhas_ioc else '<p class="vazio">Nenhum indicador no período.</p>'}""")

    partes.append("""<h2>Metodologia e limitações</h2><div class="destaque"><ul>
<li>Detecção por nome de domínio nos CT logs: só aparece o que tem certificado e cita (ou imita) a marca.</li>
<li>O servidor de CT logs roda limitado a 1 núcleo: nos picos, parte dos certificados é descartada.</li>
<li>Nota de risco: sinais combinados como chances independentes, com pesos explícitos (python -m risco pesos).</li>
<li>Campanhas por molde: domínios com a mesma parte fixa no subdomínio; dois golpistas diferentes podem usar
moldes parecidos.</li>
<li>Nenhum endereço foi acessado: a análise usa o nome, o certificado e o conteúdo das mensagens.</li>
</ul></div>""")
    partes.append(f"<footer>Gerado pelo Radar Phishing em {dados.fim.astimezone():%d/%m/%Y %H:%M}. "
                  "Dados públicos (CT logs) e mensagens próprias ou autorizadas, conforme a LGPD.</footer>"
                  "</main></body></html>")
    return "\n".join(partes)
