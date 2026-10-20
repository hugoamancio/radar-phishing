-- ---------------------------------------------------------------------------
--  Etapa 1 - Monitor de dominios
--
--  Banco ja criado antes desta etapa? O Postgres so roda docker-entrypoint-
--  initdb.d no primeiro start, entao aplique na mao:
--    docker exec -i radar_db psql -U analista -d radar < sql/03_monitor_dominios.sql
-- ---------------------------------------------------------------------------

-- O mesmo certificado aparece em varios logs (e como precert e cert final).
-- O serial identifica o certificado; a dupla (dominio, serial) evita
-- gravar a mesma emissao varias vezes.
ALTER TABLE certificado
    ADD COLUMN IF NOT EXISTS serial TEXT,
    ADD COLUMN IF NOT EXISTS log_ct TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS certificado_dominio_serial
    ON certificado (dominio_id, serial);

-- Por que o dominio foi considerado suspeito. Uma linha por (dominio, marca):
-- se o dominio voltar a aparecer, as tecnicas sao atualizadas, nao duplicadas.
CREATE TABLE IF NOT EXISTS deteccao_dominio (
    id            BIGSERIAL   PRIMARY KEY,
    dominio_id    BIGINT      NOT NULL REFERENCES dominio(id),
    marca_id      SMALLINT    NOT NULL REFERENCES marca(id),
    tecnicas      TEXT[]      NOT NULL,     -- {"marca_no_dominio", "palavra_isca"}
    motivos       JSONB       NOT NULL,     -- [{"tecnica": ..., "detalhe": ...}]
    trecho        TEXT        NOT NULL,     -- parte do dominio que imita a marca
    detectado_em  TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (dominio_id, marca_id)
);

CREATE INDEX IF NOT EXISTS deteccao_dominio_recentes
    ON deteccao_dominio (detectado_em DESC);

-- Visao pronta para consulta e, mais tarde, para o dashboard.
CREATE OR REPLACE VIEW vw_dominios_suspeitos AS
SELECT d.nome            AS dominio,
       m.nome            AS marca,
       dd.tecnicas,
       dd.trecho,
       dd.detectado_em,
       c.emissor,
       c.log_ct
FROM deteccao_dominio dd
JOIN dominio d ON d.id = dd.dominio_id
JOIN marca   m ON m.id = dd.marca_id
LEFT JOIN LATERAL (
    SELECT emissor, log_ct
    FROM certificado
    WHERE dominio_id = d.id
    ORDER BY visto_em DESC
    LIMIT 1
) c ON true
ORDER BY dd.detectado_em DESC;
