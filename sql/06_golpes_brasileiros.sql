-- ---------------------------------------------------------------------------
--  Etapa 4 - Golpes brasileiros: SMS/WhatsApp, boleto falso e QR Code de Pix
--
--  Banco ja criado antes desta etapa? Aplique na mao:
--    docker exec -i radar_db psql -U analista -d radar < sql/06_golpes_brasileiros.sql
-- ---------------------------------------------------------------------------

-- Codigo FEBRABAN de cada banco: um "boleto do Bradesco" tem de comecar com 237.
ALTER TABLE marca ADD COLUMN IF NOT EXISTS codigo_banco TEXT;
UPDATE marca SET codigo_banco = '237' WHERE nome = 'Bradesco';

-- SMS e WhatsApp analisados. LGPD: como no e-mail, o TEXTO da mensagem nao e
-- gravado (pode trazer nome, CPF, numero do cartao). Ficam o hash, o canal,
-- os links e os sinais.
CREATE TABLE IF NOT EXISTS mensagem (
    id            BIGSERIAL   PRIMARY KEY,
    texto_sha256  TEXT        NOT NULL UNIQUE,
    canal         TEXT        NOT NULL CHECK (canal IN ('sms', 'whatsapp', 'outro')),
    remetente     TEXT,                         -- numero curto ou telefone, se informado
    achados       JSONB       NOT NULL DEFAULT '[]',
    analisada_em  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS link_mensagem (
    id           BIGSERIAL PRIMARY KEY,
    mensagem_id  BIGINT    NOT NULL REFERENCES mensagem(id) ON DELETE CASCADE,
    dominio_id   BIGINT    NOT NULL REFERENCES dominio(id),
    url          TEXT      NOT NULL
);
CREATE INDEX IF NOT EXISTS link_mensagem_dominio ON link_mensagem (dominio_id);

-- A nota de risco de uma mensagem entra na mesma tabela de avaliacoes.
ALTER TABLE avaliacao_risco ADD COLUMN IF NOT EXISTS mensagem_id BIGINT REFERENCES mensagem(id);
ALTER TABLE avaliacao_risco DROP CONSTRAINT IF EXISTS avaliacao_risco_check;
ALTER TABLE avaliacao_risco ADD CONSTRAINT avaliacao_risco_alvo CHECK (
    num_nonnulls(dominio_id, email_id, mensagem_id) = 1);
CREATE INDEX IF NOT EXISTS avaliacao_risco_mensagem ON avaliacao_risco (mensagem_id, avaliado_em DESC);

-- vw_risco_atual passa a separar tambem por mensagem. As visoes que dependem
-- dela sao recriadas na mesma ordem.
DROP VIEW IF EXISTS vw_dominios_suspeitos, vw_emails_analisados, vw_risco_atual;

CREATE VIEW vw_risco_atual AS
SELECT DISTINCT ON (dominio_id, email_id, mensagem_id)
       id, dominio_id, email_id, mensagem_id, nota, nivel, motivos, modelo, avaliado_em
FROM avaliacao_risco
ORDER BY dominio_id, email_id, mensagem_id, avaliado_em DESC, id DESC;

CREATE VIEW vw_dominios_suspeitos AS
SELECT d.nome AS dominio, m.nome AS marca, dd.tecnicas, dd.trecho, dd.detectado_em,
       c.emissor, c.log_ct, r.nota, r.nivel
FROM deteccao_dominio dd
JOIN dominio d ON d.id = dd.dominio_id
JOIN marca   m ON m.id = dd.marca_id
LEFT JOIN LATERAL (
    SELECT emissor, log_ct FROM certificado WHERE dominio_id = d.id ORDER BY visto_em DESC LIMIT 1
) c ON true
LEFT JOIN vw_risco_atual r ON r.dominio_id = d.id
ORDER BY dd.detectado_em DESC;

CREATE VIEW vw_emails_analisados AS
SELECT e.id, e.recebido_em, e.remetente_nome, e.remetente, e.assunto, e.spf, e.dkim, e.dmarc,
       jsonb_array_length(e.achados) AS sinais,
       (SELECT count(*) FROM jsonb_array_elements(e.achados) a WHERE a->>'gravidade' = 'alta') AS sinais_graves,
       (SELECT count(*) FROM link_email l WHERE l.email_id = e.id) AS links,
       e.analisado_em, r.nota, r.nivel
FROM email e
LEFT JOIN vw_risco_atual r ON r.email_id = e.id
ORDER BY e.analisado_em DESC;

CREATE VIEW vw_mensagens_analisadas AS
SELECT ms.id, ms.canal, ms.remetente, ms.analisada_em,
       jsonb_array_length(ms.achados) AS sinais,
       (SELECT count(*) FROM link_mensagem l WHERE l.mensagem_id = ms.id) AS links,
       r.nota, r.nivel
FROM mensagem ms
LEFT JOIN vw_risco_atual r ON r.mensagem_id = ms.id
ORDER BY ms.analisada_em DESC;
