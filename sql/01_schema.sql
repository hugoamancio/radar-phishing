-- ---------------------------------------------------------------------------
--  Radar Phishing - esquema inicial (Fase 0)
--
--  Ponto central do projeto: o mesmo dominio pode chegar por duas frentes
--  (certificado novo no CT log e link dentro de um e-mail). Por isso
--  `dominio` e uma tabela propria, e as duas frentes apontam para ela.
--  E esse cruzamento que responde "o site falso ja era conhecido antes de
--  o e-mail chegar?".
-- ---------------------------------------------------------------------------

-- Bancos que o sistema protege e os termos que identificam cada marca.
CREATE TABLE marca (
    id            SMALLSERIAL PRIMARY KEY,
    nome          TEXT        NOT NULL UNIQUE,          -- "Bradesco"
    dominios_oficiais TEXT[]  NOT NULL,                 -- {"bradesco.com.br", ...}
    palavras_chave    TEXT[]  NOT NULL                  -- {"bradesco", "bradesc0", ...}
);

-- Todo dominio visto, venha de onde vier.
CREATE TABLE dominio (
    id              BIGSERIAL   PRIMARY KEY,
    nome            TEXT        NOT NULL UNIQUE,        -- sempre em minusculas
    primeiro_visto  TIMESTAMPTZ NOT NULL DEFAULT now(),
    marca_id        SMALLINT    REFERENCES marca(id)
);

-- Frente 1: certificados emitidos (CT logs).
CREATE TABLE certificado (
    id            BIGSERIAL   PRIMARY KEY,
    dominio_id    BIGINT      NOT NULL REFERENCES dominio(id),
    emissor       TEXT,
    emitido_em    TIMESTAMPTZ,
    visto_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
    fonte         TEXT        NOT NULL                  -- "certstream", "crt.sh"
);

-- Frente 2: e-mails analisados (apenas proprios ou autorizados).
CREATE TABLE email (
    id            BIGSERIAL   PRIMARY KEY,
    message_id    TEXT        UNIQUE,
    remetente     TEXT,
    assunto       TEXT,
    recebido_em   TIMESTAMPTZ,
    spf           TEXT,                                 -- pass / fail / softfail / none
    dkim          TEXT,
    dmarc         TEXT,
    analisado_em  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Links extraidos dos e-mails, ligados ao dominio de destino.
CREATE TABLE link_email (
    id            BIGSERIAL PRIMARY KEY,
    email_id      BIGINT    NOT NULL REFERENCES email(id) ON DELETE CASCADE,
    dominio_id    BIGINT    NOT NULL REFERENCES dominio(id),
    url           TEXT      NOT NULL,
    texto_visivel TEXT                                  -- o que o usuario ve no e-mail
);

-- Saida do motor de risco: uma nota por ameaca, com os motivos.
CREATE TABLE avaliacao_risco (
    id            BIGSERIAL   PRIMARY KEY,
    dominio_id    BIGINT      REFERENCES dominio(id),
    email_id      BIGINT      REFERENCES email(id),
    nota          SMALLINT    NOT NULL CHECK (nota BETWEEN 0 AND 100),
    motivos       JSONB       NOT NULL,                 -- [{"regra": "...", "peso": 30}, ...]
    avaliado_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (dominio_id IS NOT NULL OR email_id IS NOT NULL)
);

CREATE INDEX ON certificado (dominio_id);
CREATE INDEX ON link_email (dominio_id);
CREATE INDEX ON avaliacao_risco (nota DESC);
