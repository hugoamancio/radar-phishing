"""Motor de risco: transforma sinais numa nota de 0 a 100, com os motivos.

Como a nota e calculada
-----------------------
Cada sinal tem um peso de 0 a 100: "sozinho, quanto ele indica golpe".
Os sinais se combinam como chances independentes (o chamado "OU com ruido"):

    nota = 100 x (1 - (1 - p1) x (1 - p2) x ... x (1 - pn))

Exemplo: sinais de 40 e 30 -> 100 x (1 - 0,6 x 0,7) = 58.
Duas propriedades que importam:
- a nota so sobe quando um sinal e adicionado, e nunca passa de 100;
- dez sinais fracos nao valem automaticamente o mesmo que um forte.

Sinais da mesma familia contam pela metade a partir do segundo. Exemplo:
"link disfarcado" e "link imita a marca" quase sempre falam do MESMO link;
somar os dois por inteiro seria contar a mesma prova duas vezes.

A nota maxima exibida e 99: nenhum conjunto de sinais e certeza absoluta.

A explicacao ("motivos") mostra quantos pontos cada sinal acrescentou, na
ordem em que foram somados (do mais forte para o mais fraco). A soma das
contribuicoes e a nota.
"""

from __future__ import annotations

from dataclasses import dataclass, field

VERSAO = "risco-v2"   # v2: sinais de boleto, Pix, QR Code, SMS e WhatsApp

# tecnica: (peso, familia, nome para a tela)
# Os pesos sao a parte "opiniao" do modelo; ficam aqui, num lugar so, com o
# raciocinio ao lado, para poderem ser revistos e recalculados (python -m risco reavaliar).
PESOS: dict[str, tuple[int, str, str]] = {
    # --- Dominio (monitor dos CT logs) -------------------------------------
    "homografo":            (85, "imitacao", "Homógrafo"),             # so existe para enganar o olho
    "subdominio_enganoso":  (80, "imitacao", "Subdomínio enganoso"),   # endereço oficial usado de fachada
    "marca_em_subdominio":  (70, "imitacao", "Marca só no subdomínio"),  # padrao real mais comum (19/10/2026)
    "troca_de_caracteres":  (60, "imitacao", "Troca de caracteres"),
    "erro_de_digitacao":    (45, "imitacao", "Erro de digitação"),     # mais sujeito a coincidencia
    "marca_no_dominio":     (40, "imitacao", "Marca no domínio"),      # blogs e lojas citam o banco
    "palavra_isca":         (30, "isca", "Palavra-isca"),
    "tld_suspeito":         (25, "tld", "TLD suspeito"),         # familia propria: independe das palavras

    # --- E-mail: remetente ---------------------------------------------------
    "endereco_oficial_falsificado": (90, "identidade", "Endereço oficial falsificado"),
    "dominio_imita_marca":  (60, "identidade", "Domínio do remetente imita a marca"),
    "nome_falso":           (55, "identidade", "Nome falso de remetente"),
    "sem_remetente":        (30, "identidade", "Sem remetente válido"),
    "resposta_desviada":    (25, "identidade", "Resposta desviada"),

    # --- E-mail: autenticacao ------------------------------------------------
    "dmarc_falhou":         (45, "autenticacao", "DMARC falhou"),
    "dkim_falhou":          (30, "autenticacao", "DKIM falhou"),
    "spf_falhou":           (25, "autenticacao", "SPF falhou"),
    "sem_autenticacao":     (15, "autenticacao", "Sem autenticação"),

    # --- E-mail: links -------------------------------------------------------
    "arroba_na_url":        (75, "links", "Endereço com @ enganoso"),
    "link_disfarcado":      (70, "links", "Link disfarçado"),
    "link_imita_marca":     (70, "links", "Link imita a marca"),
    "link_para_ip":         (40, "links", "Link para número de IP"),
    "link_punycode":        (40, "links", "Link com letras disfarçadas"),
    "encurtador":           (25, "links", "Link encurtado"),
    "link_sem_https":       (10, "links", "Link sem HTTPS"),

    # --- E-mail: linguagem ---------------------------------------------------
    "dados":                (40, "linguagem", "Pedido de dados sensíveis"),
    "combinacao_classica":  (35, "linguagem", "Combinação clássica de golpe"),
    "ameaca":               (30, "linguagem", "Ameaça de bloqueio ou perda"),
    "urgencia":             (20, "linguagem", "Pressão de tempo"),
    "recompensa":           (20, "linguagem", "Promessa de prêmio"),

    "link_ja_conhecido":    (90, "links", "Link já conhecido como golpe"),   # cruzamento com o monitor
    "qrcode_esconde_link":  (30, "links", "Link escondido em QR Code"),

    # --- Golpes brasileiros (e-mail, SMS e WhatsApp) -------------------------
    "falso_parente":        (65, "linguagem", "Golpe do falso parente"),     # "mudei de numero" sozinho ja e quase certeza
    "pedido_pix":           (35, "linguagem", "Pedido de Pix"),
    "compra_falsa":         (40, "linguagem", "Falso alerta de compra"),
    "pede_ligacao":         (35, "linguagem", "Pede para ligar para outro número"),
    "remetente_celular_comum": (30, "identidade", "SMS de banco vindo de celular comum"),
    "boleto_adulterado":    (85, "boleto", "Boleto adulterado"),             # DV errado: alguem mexeu nos digitos
    "boleto_banco_divergente": (80, "boleto", "Boleto de outro banco"),
    "boleto_valor_divergente": (40, "boleto", "Valor do boleto diferente do texto"),
    "pix_recebedor_divergente": (80, "pix", "Pix vai para outra pessoa"),
    "pix_alterado":         (45, "pix", "Código Pix alterado"),

    # --- E-mail: anexos ------------------------------------------------------
    "extensao_dupla":       (85, "anexos", "Programa disfarçado"),
    "anexo_executavel":     (75, "anexos", "Anexo executável"),
    "anexo_arriscado":      (30, "anexos", "Anexo arriscado"),
}

FATOR_REPETICAO = 0.5   # segundo sinal em diante da mesma familia
NOTA_MAXIMA = 99

# (nota minima, nivel). Lidos de cima para baixo.
NIVEIS = ((85, "critico"), (60, "alto"), (30, "medio"), (0, "baixo"))
NOMES_NIVEIS = {"critico": "Crítico", "alto": "Alto", "medio": "Médio", "baixo": "Baixo"}


@dataclass(frozen=True)
class Contribuicao:
    tecnica: str
    nome: str
    peso: int          # peso usado de fato (ja reduzido, se repetiu a familia)
    pontos: int        # quanto este sinal acrescentou a nota


@dataclass
class Avaliacao:
    nota: int
    nivel: str
    contribuicoes: list[Contribuicao] = field(default_factory=list)
    ignoradas: list[str] = field(default_factory=list)   # tecnicas sem peso cadastrado
    modelo: str = VERSAO

    @property
    def nome_nivel(self) -> str:
        return NOMES_NIVEIS[self.nivel]

    def motivos(self) -> list[dict]:
        return [{"tecnica": c.tecnica, "peso": c.peso, "pontos": c.pontos} for c in self.contribuicoes]


def nivel_da_nota(nota: int) -> str:
    return next(nivel for minimo, nivel in NIVEIS if nota >= minimo)


def calcular(tecnicas: list[str]) -> Avaliacao:
    """Nota de 0 a 99 para um conjunto de tecnicas (de dominio ou de e-mail)."""
    unicas = list(dict.fromkeys(tecnicas))
    conhecidas = sorted((t for t in unicas if t in PESOS), key=lambda t: -PESOS[t][0])
    ignoradas = [t for t in unicas if t not in PESOS]

    # 1o passo: peso efetivo (o mais forte de cada familia inteiro, os outros pela metade).
    familias_vistas: set[str] = set()
    efetivos: list[tuple[str, float]] = []
    for tecnica in conhecidas:
        peso, familia, _ = PESOS[tecnica]
        efetivos.append((tecnica, peso * (FATOR_REPETICAO if familia in familias_vistas else 1.0)))
        familias_vistas.add(familia)
    # 2o passo: somar do maior peso EFETIVO para o menor, que e a ordem da explicacao.
    # (Pela ordem nominal, um sinal reduzido aparecia acima de outro que somou mais.)
    efetivos.sort(key=lambda x: -x[1])

    chance_nao_golpe = 1.0
    acumulado = 0.0
    contribuicoes: list[Contribuicao] = []
    for tecnica, efetivo in efetivos:
        nome = PESOS[tecnica][2]
        chance_nao_golpe *= 1 - efetivo / 100
        nova = 100 * (1 - chance_nao_golpe)
        # Diferenca entre notas ja arredondadas: assim a soma dos pontos e exatamente a nota.
        contribuicoes.append(Contribuicao(tecnica, nome, round(efetivo), round(nova) - round(acumulado)))
        acumulado = nova

    nota = min(NOTA_MAXIMA, round(acumulado))
    # O corte em 99 sai dos ultimos sinais que tem ponto para ceder, nunca
    # deixando contribuicao negativa: a soma continua batendo com a nota.
    excesso = round(acumulado) - nota
    for i in range(len(contribuicoes) - 1, -1, -1):
        if excesso <= 0:
            break
        c = contribuicoes[i]
        tirar = min(c.pontos, excesso)
        contribuicoes[i] = Contribuicao(c.tecnica, c.nome, c.peso, c.pontos - tirar)
        excesso -= tirar
    return Avaliacao(nota, nivel_da_nota(nota), contribuicoes, ignoradas)
