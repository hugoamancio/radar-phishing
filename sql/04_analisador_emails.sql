-- ---------------------------------------------------------------------------
--  Etapa 2 - Analisador de e-mails
--
--  Banco ja criado antes desta etapa? Aplique na mao:
--    docker exec -i radar_db psql -U analista -d radar < sql/04_analisador_emails.sql
--
--  LGPD: o corpo do e-mail NUNCA e gravado. Fica so o necessario para a
--  analise e o cruzamento: remetente, assunto, autenticacao, links e achados.
--  O arquivo e identificado pelo hash SHA-256, sem guardar o conteudo.
-- ---------------------------------------------------------------------------

ALTER TABLE email
    ADD COLUMN IF NOT EXISTS arquivo_sha256  TEXT,
    ADD COLUMN IF NOT EXISTS remetente_nome  TEXT,
    ADD COLUMN IF NOT EXISTS reply_to        TEXT,
    ADD COLUMN IF NOT EXISTS dmarc_politica  TEXT,
    ADD COLUMN IF NOT EXISTS achados         JSONB NOT NULL DEFAULT '[]';

-- O mesmo e-mail salvo duas vezes (ou encaminhado) gera arquivos diferentes
-- com o mesmo Message-ID; quem identifica a linha e o hash do arquivo.
ALTER TABLE email DROP CONSTRAINT IF EXISTS email_message_id_key;
CREATE INDEX IF NOT EXISTS email_message_id ON email (message_id);

-- O mesmo arquivo analisado duas vezes atualiza a linha em vez de duplicar.
CREATE UNIQUE INDEX IF NOT EXISTS email_arquivo_sha256 ON email (arquivo_sha256);

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
       e.analisado_em
FROM email e
ORDER BY e.analisado_em DESC;
