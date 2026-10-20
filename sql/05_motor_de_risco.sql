-- ---------------------------------------------------------------------------
--  Etapa 3 - Motor de risco
--
--  Banco ja criado antes desta etapa? Aplique na mao:
--    docker exec -i radar_db psql -U analista -d radar < sql/05_motor_de_risco.sql
--
--  Cada avaliacao e uma linha nova (historico). A versao do modelo fica junto:
--  se os pesos mudarem, `python -m risco reavaliar` grava a nota nova sem
--  apagar a antiga, e da para comparar.
-- ---------------------------------------------------------------------------

ALTER TABLE avaliacao_risco
    ADD COLUMN IF NOT EXISTS nivel  TEXT,
    ADD COLUMN IF NOT EXISTS modelo TEXT;

CREATE INDEX IF NOT EXISTS avaliacao_risco_dominio ON avaliacao_risco (dominio_id, avaliado_em DESC);
CREATE INDEX IF NOT EXISTS avaliacao_risco_email   ON avaliacao_risco (email_id, avaliado_em DESC);

-- Avaliacao mais recente de cada dominio e de cada e-mail.
CREATE OR REPLACE VIEW vw_risco_atual AS
SELECT DISTINCT ON (dominio_id, email_id)
       id, dominio_id, email_id, nota, nivel, motivos, modelo, avaliado_em
FROM avaliacao_risco
ORDER BY dominio_id, email_id, avaliado_em DESC, id DESC;

-- As visoes das etapas 1 e 2 ganham a nota (colunas novas sempre no fim:
-- CREATE OR REPLACE VIEW nao deixa mudar a ordem das antigas).
CREATE OR REPLACE VIEW vw_dominios_suspeitos AS
SELECT d.nome            AS dominio,
       m.nome            AS marca,
       dd.tecnicas,
       dd.trecho,
       dd.detectado_em,
       c.emissor,
       c.log_ct,
       r.nota,
       r.nivel
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
LEFT JOIN vw_risco_atual r ON r.dominio_id = d.id AND r.email_id IS NULL
ORDER BY dd.detectado_em DESC;

CREATE OR REPLACE VIEW vw_emails_analisados AS
SELECT e.id,
       e.recebido_em,
       e.remetente_nome,
       e.remetente,
       e.assunto,
       e.spf, e.dkim, e.dmarc,
       jsonb_array_length(e.achados)                                        AS sinais,
       (SELECT count(*) FROM jsonb_array_elements(e.achados) a
         WHERE a->>'gravidade' = 'alta')                                    AS sinais_graves,
       (SELECT count(*) FROM link_email l WHERE l.email_id = e.id)          AS links,
       e.analisado_em,
       r.nota,
       r.nivel
FROM email e
LEFT JOIN vw_risco_atual r ON r.email_id = e.id AND r.dominio_id IS NULL
ORDER BY e.analisado_em DESC;
