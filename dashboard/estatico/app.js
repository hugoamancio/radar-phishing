/* Radar Phishing · dashboard
 *
 * Sem bibliotecas externas: graficos desenhados em SVG aqui mesmo.
 * Seguranca: todo dado vindo do banco entra como TEXTO (textContent), nunca
 * como HTML. Um dominio de golpe com um nome estranho nao vira codigo.
 */
"use strict";

const SVG = "http://www.w3.org/2000/svg";
const ATUALIZAR_A_CADA_MS = 15000;
const NOMES_NIVEL = { baixo: "Baixo", medio: "Médio", alto: "Alto", critico: "Crítico" };
const NOMES_CANAL = { "e-mail": "E-mail", sms: "SMS", whatsapp: "WhatsApp", outro: "Mensagem" };

/* ---------- utilidades ---------- */

function el(tag, classe, ...filhos) {
  const n = document.createElement(tag);
  if (classe) n.className = classe;
  for (const f of filhos) if (f != null) n.append(f instanceof Node ? f : document.createTextNode(String(f)));
  return n;
}

function svg(tag, atributos = {}) {
  const n = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(atributos)) n.setAttribute(k, v);
  return n;
}

function limpar(n) { while (n.firstChild) n.removeChild(n.firstChild); return n; }

function numero(n) { return Number(n || 0).toLocaleString("pt-BR"); }

function haQuanto(iso) {
  if (!iso) return "—";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `há ${Math.round(s)} s`;
  if (s < 3600) return `há ${Math.round(s / 60)} min`;
  if (s < 86400) return `há ${Math.round(s / 3600)} h`;
  const d = Math.round(s / 86400);
  return `há ${d} dia${d > 1 ? "s" : ""}`;
}

function dataCurta(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }) + " " +
         d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

async function buscar(caminho) {
  const r = await fetch(caminho, { headers: { Accept: "application/json" } });
  if (!r.ok) throw new Error(`${caminho}: ${r.status}`);
  return r.json();
}

/* ---------- dica (tooltip) ---------- */

const dica = document.getElementById("dica");
function mostrarDica(evento, titulo, texto) {
  limpar(dica).append(el("strong", null, titulo), el("div", null, texto));
  dica.hidden = false;
  const x = Math.min(evento.clientX + 14, window.innerWidth - dica.offsetWidth - 8);
  dica.style.left = `${x}px`;
  dica.style.top = `${evento.clientY + 14}px`;
}
function esconderDica() { dica.hidden = true; }

/* ---------- selo de risco: 5 segmentos + nota + nivel escrito ---------- */

function selo(nota, nivel) {
  if (nota == null) return el("span", "td-apagado", "—");
  const caixa = el("span", `risco nivel-${nivel}`);
  const segmentos = el("span", "risco-segmentos");
  const ligados = Math.round(nota / 20);
  for (let i = 0; i < 5; i++) segmentos.append(el("i", i < ligados ? "ligado" : ""));
  caixa.append(segmentos, el("span", "risco-nota", nota), el("span", "risco-nome", NOMES_NIVEL[nivel] || ""));
  caixa.setAttribute("aria-label", `risco ${nota}, ${NOMES_NIVEL[nivel] || ""}`);
  return caixa;
}

/* Dominio com o trecho que imita a marca destacado. */
function dominioDestacado(dominio, trecho) {
  const caixa = el("span");
  const pos = trecho ? dominio.indexOf(trecho) : -1;
  if (pos < 0) { caixa.append(dominio); return caixa; }
  caixa.append(dominio.slice(0, pos), el("mark", null, trecho), dominio.slice(pos + trecho.length));
  return caixa;
}

/* ---------- grafico de linha: deteccoes por dia ---------- */

function escalaBonita(maximo) {
  // Contagem nao tem meio dominio: ate 20, o topo e multiplo de 4 e as 4 divisoes sao inteiras.
  if (maximo <= 20) return Math.max(4, Math.ceil(maximo / 4) * 4);
  const base = 10 ** Math.floor(Math.log10(maximo));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * base >= maximo) return m * base;
  return 10 * base;
}

function desenharSerie(dados) {
  const alvo = limpar(document.getElementById("grafico-serie"));
  const largura = alvo.clientWidth || 600, altura = alvo.clientHeight || 240;
  const m = { esq: 36, dir: 14, topo: 14, base: 28 };
  const w = largura - m.esq - m.dir, h = altura - m.topo - m.base;
  const maximo = escalaBonita(Math.max(1, ...dados.map((d) => d.total)));
  const x = (i) => m.esq + (dados.length === 1 ? w / 2 : (i * w) / (dados.length - 1));
  const y = (v) => m.topo + h - (v / maximo) * h;

  const raiz = svg("svg", { viewBox: `0 0 ${largura} ${altura}`, preserveAspectRatio: "none" });
  const defs = svg("defs");
  const gradiente = svg("linearGradient", { id: "area-neon", x1: 0, x2: 0, y1: 0, y2: 1 });
  gradiente.append(svg("stop", { offset: "0%", "stop-color": "#39ff14", "stop-opacity": 0.32 }),
                   svg("stop", { offset: "100%", "stop-color": "#39ff14", "stop-opacity": 0 }));
  const brilho = svg("filter", { id: "brilho", x: "-20%", y: "-50%", width: "140%", height: "200%" });
  brilho.append(svg("feGaussianBlur", { stdDeviation: 3, result: "b" }));
  const mescla = svg("feMerge");
  mescla.append(svg("feMergeNode", { in: "b" }), svg("feMergeNode", { in: "SourceGraphic" }));
  brilho.append(mescla);
  defs.append(gradiente, brilho);
  raiz.append(defs);

  // Grade recessiva e eixo Y (4 divisoes).
  const eixo = svg("g", { class: "eixo" });
  for (let i = 0; i <= 4; i++) {
    const v = (maximo * i) / 4, yy = y(v);
    raiz.append(svg("line", { class: i === 0 ? "linha-base" : "linha-grade", x1: m.esq, x2: largura - m.dir, y1: yy, y2: yy }));
    const t = svg("text", { x: m.esq - 8, y: yy + 4, "text-anchor": "end" });
    t.textContent = Number.isInteger(v) ? v : v.toFixed(1);
    eixo.append(t);
  }
  // Eixo X: um rotulo a cada 2 dias, para nao amontoar.
  dados.forEach((d, i) => {
    if (i % 2 !== (dados.length - 1) % 2) return;
    const t = svg("text", { x: x(i), y: altura - 8, "text-anchor": "middle" });
    const [ano, mes, dia] = d.dia.split("-");
    t.textContent = `${dia}/${mes}`;
    eixo.append(t);
  });
  raiz.append(eixo);

  const pontos = dados.map((d, i) => `${x(i)},${y(d.total)}`);
  raiz.append(svg("path", { d: `M${x(0)},${y(0)} L${pontos.join(" L")} L${x(dados.length - 1)},${y(0)} Z`, fill: "url(#area-neon)" }));
  raiz.append(svg("path", { class: "serie-linha", d: `M${pontos.join(" L")}`, filter: "url(#brilho)" }));

  // Ultimo ponto rotulado (rotulo direto seletivo: so o valor de hoje).
  const ultimo = dados.length - 1;
  raiz.append(svg("circle", { class: "serie-ponto", cx: x(ultimo), cy: y(dados[ultimo].total), r: 4 }));
  const rotuloHoje = svg("text", { x: x(ultimo) - 10, y: y(dados[ultimo].total) + 4, "text-anchor": "end", class: "rotulo-hoje" });
  rotuloHoje.textContent = `hoje: ${dados[ultimo].total}`;
  raiz.append(rotuloHoje);

  // Camada de interacao: mira vertical + ponto + dica no dia mais proximo.
  const mira = svg("line", { class: "mira", y1: m.topo, y2: m.topo + h, visibility: "hidden" });
  const ponto = svg("circle", { class: "serie-ponto", r: 5, visibility: "hidden" });
  const camada = svg("rect", { class: "alvo", x: m.esq, y: m.topo, width: w, height: h });
  raiz.append(mira, ponto, camada);
  camada.addEventListener("mousemove", (e) => {
    const caixa = raiz.getBoundingClientRect();
    const px = ((e.clientX - caixa.left) / caixa.width) * largura;
    const i = Math.max(0, Math.min(dados.length - 1, Math.round(((px - m.esq) / w) * (dados.length - 1))));
    mira.setAttribute("x1", x(i)); mira.setAttribute("x2", x(i)); mira.setAttribute("visibility", "visible");
    ponto.setAttribute("cx", x(i)); ponto.setAttribute("cy", y(dados[i].total)); ponto.setAttribute("visibility", "visible");
    const [ano, mes, dia] = dados[i].dia.split("-");
    mostrarDica(e, `${dia}/${mes}/${ano}`, `${dados[i].total} domínio${dados[i].total === 1 ? "" : "s"} suspeito${dados[i].total === 1 ? "" : "s"}`);
  });
  camada.addEventListener("mouseleave", () => { mira.setAttribute("visibility", "hidden"); ponto.setAttribute("visibility", "hidden"); esconderDica(); });
  alvo.append(raiz);
}

/* ---------- barras horizontais ---------- */

function desenharBarras(id, itens, { cor, sufixo = "" } = {}) {
  const alvo = limpar(document.getElementById(id));
  if (!itens.length) { alvo.append(el("p", "vazio", "Nada ainda.")); return; }
  const maximo = Math.max(...itens.map((i) => i.total), 1);
  const soma = itens.reduce((s, i) => s + i.total, 0) || 1;
  for (const item of itens) {
    const linha = el("div", "barra-linha");
    const preenchida = el("div", "barra-preenchida");
    preenchida.style.width = "0%";
    if (cor) preenchida.style.background = cor(item);
    const trilho = el("div", "barra-trilho", preenchida);
    linha.append(el("span", "barra-nome", item.nome),
                 el("span", "barra-valor", `${numero(item.total)}${sufixo}  ·  ${Math.round((item.total / soma) * 100)}%`),
                 trilho);
    linha.addEventListener("mousemove", (e) => mostrarDica(e, item.nome, `${numero(item.total)} de ${numero(soma)} (${Math.round((item.total / soma) * 100)}%)`));
    linha.addEventListener("mouseleave", esconderDica);
    alvo.append(linha);
    // Zero e zero: so valores positivos ganham a largura minima para continuarem visiveis.
    requestAnimationFrame(() => { preenchida.style.width = item.total ? `${Math.max(2, (item.total / maximo) * 100)}%` : "0%"; });
  }
}

const COR_NIVEL = { baixo: "#1a6b2a", medio: "#26a33a", alto: "#2fd94a", critico: "#39ff14" };

/* Legenda das faixas de nota: explica o que cada nivel quer dizer. */
const FAIXAS = [
  ["critico", "85–99", "golpe quase certo"], ["alto", "60–84", "provável golpe"],
  ["medio", "30–59", "atenção, pode ser legítimo"], ["baixo", "0–29", "sem sinais fortes"],
];
function desenharFaixas() {
  const alvo = document.getElementById("faixas-risco");
  if (alvo.childNodes.length) return;
  for (const [nivel, faixa, texto] of FAIXAS) {
    const amostra = el("i", "faixa-amostra");
    amostra.style.background = COR_NIVEL[nivel];
    alvo.append(el("li", null, amostra, el("span", "faixa-nome", NOMES_NIVEL[nivel]),
                   el("span", "faixa-intervalo", faixa), el("span", "faixa-texto", texto)));
  }
}

/* ---------- cruzamento: anel + linha do tempo ---------- */

function desenharCruzamento(resumo, itens) {
  const anel = limpar(document.getElementById("anel-cruzamento"));
  const taxa = resumo.taxa;
  const raio = 64, circ = 2 * Math.PI * raio;
  const s = svg("svg", { viewBox: "0 0 160 160", role: "img", "aria-label": "Proporção de golpes conhecidos antes de chegar" });
  s.append(svg("circle", { class: "anel-trilho", cx: 80, cy: 80, r: raio }));
  const valor = svg("circle", { class: "anel-valor", cx: 80, cy: 80, r: raio, transform: "rotate(-90 80 80)",
                                "stroke-dasharray": circ, "stroke-dashoffset": circ });
  s.append(valor);
  const num = svg("text", { class: "anel-numero", x: 80, y: 86, "text-anchor": "middle" });
  num.textContent = taxa == null ? "—" : `${Math.round(taxa * 100)}%`;
  const leg = svg("text", { class: "anel-legenda", x: 80, y: 104, "text-anchor": "middle" });
  leg.textContent = "ANTES DE CHEGAR";
  s.append(num, leg);
  anel.append(s, el("p", "anel-rodape", resumo.total ? `mediana: ${resumo.mediana} antes` : "sem mensagens ainda"));
  requestAnimationFrame(() => valor.setAttribute("stroke-dashoffset", circ * (1 - (taxa || 0))));

  const lista = limpar(document.getElementById("lista-cruzamento"));
  if (!itens.length) {
    lista.append(el("li", "vazio", "Nenhum golpe chegou por e-mail ou mensagem ainda. Cada link analisado é comparado com os CT logs."));
    return;
  }
  for (const c of itens.slice(0, 5)) {
    const canal = NOMES_CANAL[c.canal] || c.canal;
    const trilha = el("span", "lt-trilha");
    if (c.situacao === "antes") {
      trilha.append(el("span", null, `CT logs ${dataCurta(c.visto_nos_ct_em)}`), el("span", "lt-seta", "──"),
                    el("span", "lt-antes", `${c.antecedencia} antes`), el("span", "lt-seta", "──▶"),
                    el("span", null, `${canal} ${dataCurta(c.chegou_em)}`));
    } else if (c.situacao === "depois") {
      trilha.append(el("span", null, `${canal} ${dataCurta(c.chegou_em)}`), el("span", "lt-seta", "──"),
                    el("span", "lt-depois", `${c.antecedencia} depois`), el("span", "lt-seta", "──▶"),
                    el("span", null, `CT logs ${dataCurta(c.visto_nos_ct_em)}`));
    } else {
      trilha.append(el("span", null, `${canal} ${dataCurta(c.chegou_em)}`), el("span", null, "· nunca visto nos CT logs"));
    }
    lista.append(el("li", null, selo(c.nota, c.nivel), el("span", "lt-dominio", c.dominio), trilha));
  }
}

/* ---------- tabela e listas ---------- */

function desenharDeteccoes(itens) {
  const corpo = limpar(document.getElementById("tabela-deteccoes"));
  if (!itens.length) {
    const td = el("td", "vazio", "Nenhum domínio suspeito ainda. Deixe o monitor rodando: python -m monitor");
    td.colSpan = 5;
    corpo.append(el("tr", null, td));
    return;
  }
  for (const d of itens) {
    const tecnica = el("td", "td-tecnica", d.tecnica);
    if (d.reforcos.length) tecnica.append(el("div", "td-reforcos", "+ " + d.reforcos.join(", ")));
    const quando = el("td", "td-apagado", haQuanto(d.quando));
    quando.title = dataCurta(d.quando);
    corpo.append(el("tr", null, el("td", null, selo(d.nota, d.nivel)),
                    el("td", "td-dominio", dominioDestacado(d.visivel || d.dominio, d.trecho)),
                    tecnica, el("td", "td-emissor", d.emissor || "—"), quando));
  }
}

function desenharRecebidos(itens) {
  const lista = limpar(document.getElementById("lista-recebidos"));
  if (!itens.length) {
    lista.append(el("li", "vazio", "Nada analisado ainda. Use python -m analisador e python -m mensagem."));
    return;
  }
  for (const r of itens) {
    const topo = el("div", "rec-topo", el("span", "rec-canal", `${NOMES_CANAL[r.canal] || r.canal} · ${haQuanto(r.quando)}`), selo(r.nota, r.nivel));
    lista.append(el("li", null, topo, el("span", "rec-de", r.de || "remetente não informado"),
                    r.assunto ? el("span", "rec-assunto", r.assunto) : null));
  }
}

/* ---------- KPIs e status ---------- */

function desenharResumo(r) {
  document.getElementById("kpi-suspeitos").textContent = numero(r.suspeitos);
  document.getElementById("kpi-suspeitos-24h").textContent = `+${numero(r.suspeitos_24h)} nas últimas 24 h`;
  const criticos = r.niveis.find((n) => n.nivel === "critico")?.total || 0;
  const altos = r.niveis.find((n) => n.nivel === "alto")?.total || 0;
  document.getElementById("kpi-criticos").textContent = numero(criticos);
  document.getElementById("kpi-criticos-detalhe").textContent = `${numero(altos)} com risco alto`;
  document.getElementById("kpi-recebidos").textContent = numero(r.emails_golpe + r.mensagens_golpe);
  document.getElementById("kpi-recebidos-detalhe").textContent =
    `de ${numero(r.emails + r.mensagens)} analisados · ${numero(r.emails)} e-mails, ${numero(r.mensagens)} msgs`;
  const c = r.cruzamento;
  document.getElementById("kpi-antes").textContent = c.taxa == null ? "—" : `${Math.round(c.taxa * 100)}%`;
  document.getElementById("kpi-antes-detalhe").textContent =
    c.total ? `${c.antes} de ${c.total} · mediana ${c.mediana} antes` : "nenhum golpe recebido ainda";

  const status = document.getElementById("status");
  // O monitor bate a cada 10 s; sem batimento ha mais de 45 s, ele parou.
  const sinal = r.monitor.ultimo_sinal;
  const idade = sinal ? (Date.now() - new Date(sinal).getTime()) / 1000 : Infinity;
  const aoVivo = idade < 45;
  status.classList.toggle("ao-vivo", aoVivo);
  document.getElementById("status-texto").textContent = aoVivo
    ? `ao vivo · ${numero(r.monitor.ritmo)} certificados/s`
    : (sinal ? `monitor parado · último sinal ${haQuanto(sinal)}` : "monitor ainda não rodou");

  desenharBarras("grafico-niveis", r.niveis.slice().reverse(), { cor: (i) => COR_NIVEL[i.nivel] });
  desenharFaixas();
}

/* ---------- pesquisa ---------- */

const TITULOS = {
  conhecido: "Golpe conhecido", conhecido_pai: "Subdomínio de golpe conhecido",
  suspeito_agora: "Parece golpe", oficial: "Site oficial", nada: "Sem registro",
};

function desenharPesquisa(r) {
  const caixa = limpar(document.getElementById("resultado-busca"));
  caixa.hidden = false;
  caixa.className = `resultado-busca${r.nivel ? " nivel-" + r.nivel : ""}`;
  if (!r.dominio) {
    caixa.append(el("div", "resultado-titulo", el("strong", null, "Endereço inválido")),
                 el("p", "conselho", "Exemplos aceitos: https://site.com/login, site.com, hxxps://site[.]com"));
    return;
  }
  const titulo = el("div", "resultado-titulo", el("strong", null, TITULOS[r.tipo] || r.tipo));
  if (r.nota != null) titulo.append(selo(r.nota, r.nivel));
  caixa.append(titulo, el("div", "resultado-dominio", dominioDestacado(r.dominio, r.trecho || r.registro?.trecho)));

  const fatos = el("dl", "resultado-fatos");
  const fato = (rotulo, valor) => fatos.append(el("dt", null, rotulo), el("dd", null, valor));
  if (r.registro) {
    fato("Imita", r.registro.marca);
    fato("No banco desde", `${dataCurta(r.registro.detectado_em)} (${haQuanto(r.registro.detectado_em)})`);
    fato("Certificados vistos", `${r.registro.certificados}${r.registro.ultimo_emissor ? " · último: " + r.registro.ultimo_emissor : ""}`);
    fato("E-mails", r.registro.emails ? `apareceu em ${r.registro.emails}` : "ainda não apareceu");
    fato("SMS e WhatsApp", r.registro.mensagens ? `apareceu em ${r.registro.mensagens}` : "ainda não apareceu");
    if (r.tipo === "conhecido_pai") fato("Domínio principal", r.registro.dominio);
  } else if (r.marca) {
    fato("Imita", r.marca);
    fato("No banco", "ainda não: análise feita agora pelo detector");
  } else if (r.marca_oficial) {
    fato("Marca", r.marca_oficial);
  }
  if (fatos.childNodes.length) caixa.append(fatos);

  if (r.motivos.length) {
    const motivos = el("dl", "resultado-fatos");
    for (const m of r.motivos) motivos.append(el("dt", null, m.nome || m.tecnica), el("dd", null, m.detalhe));
    caixa.append(el("div", "rotulo", "Por que"), motivos);
  }
  const conselhos = {
    conhecido: "Não acesse o endereço e não informe nenhum dado. Se já informou, ligue para o banco pelo número do verso do cartão.",
    conhecido_pai: "Não acesse o endereço e não informe nenhum dado. Se já informou, ligue para o banco pelo número do verso do cartão.",
    suspeito_agora: "Não acesse o endereço e não informe nenhum dado. Se já informou, ligue para o banco pelo número do verso do cartão.",
    oficial: "Confira se o endereço está exatamente assim: um único caractere diferente já é outro site.",
    nada: "Não está no banco e não imita nenhuma marca monitorada. Isso não garante que o site seja seguro.",
  };
  caixa.append(el("p", "conselho", conselhos[r.tipo] || ""));
}

document.getElementById("form-busca").addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = document.getElementById("campo-busca").value.trim();
  if (!q) return;
  try {
    desenharPesquisa(await buscar(`/api/pesquisa?q=${encodeURIComponent(q)}`));
  } catch {
    const caixa = limpar(document.getElementById("resultado-busca"));
    caixa.hidden = false;
    caixa.append(el("p", "conselho", "Não foi possível pesquisar agora: o banco está indisponível."));
  }
});

/* ---------- ciclo de atualizacao ---------- */

let ultimaSerie = [];
async function atualizar() {
  try {
    const [resumo, serie, tecnicas, deteccoes, cruzamento, recebidos] = await Promise.all([
      buscar("/api/resumo"), buscar("/api/serie?dias=14"), buscar("/api/tecnicas"),
      buscar("/api/deteccoes"), buscar("/api/cruzamento"), buscar("/api/recebidos"),
    ]);
    desenharResumo(resumo);
    ultimaSerie = serie;
    desenharSerie(serie);
    desenharBarras("grafico-tecnicas", tecnicas);
    desenharDeteccoes(deteccoes);
    desenharCruzamento(resumo.cruzamento, cruzamento);
    desenharRecebidos(recebidos);
    document.getElementById("atualizado").textContent =
      `atualizado às ${new Date().toLocaleTimeString("pt-BR")} · a cada ${ATUALIZAR_A_CADA_MS / 1000} s`;
  } catch {
    document.getElementById("status").classList.remove("ao-vivo");
    document.getElementById("status-texto").textContent = "banco indisponível";
  }
}

function relogio() {
  document.getElementById("relogio").textContent = new Date().toLocaleTimeString("pt-BR");
}

let redesenho;
window.addEventListener("resize", () => {
  clearTimeout(redesenho);
  redesenho = setTimeout(() => ultimaSerie.length && desenharSerie(ultimaSerie), 150);
});

buscar("/api/estado").then((e) => { document.getElementById("faixa-demo").hidden = !e.demo; }).catch(() => {});
relogio();
setInterval(relogio, 1000);
atualizar();
setInterval(atualizar, ATUALIZAR_A_CADA_MS);
