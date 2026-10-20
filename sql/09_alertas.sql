-- ---------------------------------------------------------------------------
--  Etapa 8 - Alertas no Telegram e no Discord
--
--    docker exec -i radar_db psql -U analista -d radar < sql/09_alertas.sql
--
--  Cada alerta enviado (ou tentado) vira uma linha. Serve para tres coisas:
--  nao avisar a mesma coisa duas vezes, limitar quantos alertas saem por hora
--  e ter o historico do que foi avisado e quando.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS alerta (
    id          BIGSERIAL   PRIMARY KEY,
    tipo        TEXT        NOT NULL CHECK (tipo IN ('dominio', 'email', 'mensagem')),
    alvo_id     BIGINT      NOT NULL,           -- id em dominio, email ou mensagem
    canal       TEXT        NOT NULL CHECK (canal IN ('telegram', 'discord', 'simulacao')),
    nota        SMALLINT    NOT NULL,
    status      TEXT        NOT NULL CHECK (status IN ('enviado', 'falhou')),
    erro        TEXT,
    criado_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tipo, alvo_id, canal)
);

CREATE INDEX IF NOT EXISTS alerta_recentes ON alerta (canal, criado_em DESC);
