-- ---------------------------------------------------------------------------
--  Etapa 7 - Batimento do monitor (para o dashboard saber se ele esta vivo)
--
--    docker exec -i radar_db psql -U analista -d radar < sql/08_batimento_monitor.sql
--
--  O ultimo certificado SUSPEITO nao diz se o monitor esta rodando: um monitor
--  saudavel pode passar horas sem achar golpe. Por isso o monitor atualiza
--  esta linha unica a cada 10 segundos, achando golpe ou nao.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS monitor_batimento (
    id            SMALLINT    PRIMARY KEY DEFAULT 1 CHECK (id = 1),   -- sempre uma linha so
    ultimo_sinal  TIMESTAMPTZ NOT NULL,
    certificados  BIGINT      NOT NULL DEFAULT 0,                     -- analisados desde que ligou
    ritmo         INTEGER     NOT NULL DEFAULT 0,                     -- certificados por segundo
    iniciado_em   TIMESTAMPTZ NOT NULL
);
