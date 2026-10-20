-- ---------------------------------------------------------------------------
--  Etapa 6 - Cruzamento: o site falso ja era conhecido antes de chegar?
--
--  Banco ja criado antes desta etapa? Aplique na mao:
--    docker exec -i radar_db psql -U analista -d radar < sql/07_cruzamento.sql
--
--  Uma linha por (dominio suspeito, e-mail ou mensagem em que ele chegou).
--  Compara quando o monitor viu o certificado nos CT logs com quando o link
--  chegou ate a pessoa. "Antecedencia" positiva = o sistema ja sabia antes.
--
--  O dominio do link e o do certificado nem sempre sao identicos: o golpista
--  tira um certificado para golpe.xyz e manda login.golpe.xyz. Por isso o
--  certificado de um dominio "acima" tambem conta.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW vw_cruzamento AS
WITH chegadas AS (
    -- Data de chegada do e-mail vem do cabecalho Date, que o remetente pode
    -- falsificar; sem ele, vale o momento da analise.
    SELECT l.dominio_id, 'e-mail'::text AS canal, e.id AS origem_id, e.remetente AS de,
           COALESCE(e.recebido_em, e.analisado_em) AS chegou_em
    FROM link_email l JOIN email e ON e.id = l.email_id
    UNION ALL
    SELECT l.dominio_id, ms.canal, ms.id, ms.remetente, ms.analisada_em
    FROM link_mensagem l JOIN mensagem ms ON ms.id = l.mensagem_id
),
primeiro_ct AS (
    -- Para cada dominio que chegou, o certificado mais antigo visto para ele
    -- mesmo ou para um dominio "acima" dele.
    SELECT d.id AS dominio_id,
           min(c.visto_em) AS visto_em,
           count(c.id)     AS certificados
    FROM dominio d
    JOIN dominio dc ON dc.nome = d.nome OR d.nome LIKE '%.' || dc.nome
    JOIN certificado c ON c.dominio_id = dc.id
    WHERE d.id IN (SELECT dominio_id FROM chegadas)
    GROUP BY d.id
)
SELECT d.nome                              AS dominio,
       ch.canal,
       ch.origem_id,
       ch.de,
       ch.chegou_em,
       ct.visto_em                         AS visto_nos_ct_em,
       ct.certificados,
       ch.chegou_em - ct.visto_em          AS antecedencia,
       CASE WHEN ct.visto_em IS NULL        THEN 'desconhecido'
            WHEN ct.visto_em <= ch.chegou_em THEN 'antes'
            ELSE 'depois' END              AS situacao,
       r.nota,
       r.nivel
FROM chegadas ch
JOIN dominio d ON d.id = ch.dominio_id
LEFT JOIN primeiro_ct ct ON ct.dominio_id = d.id
LEFT JOIN vw_risco_atual r ON r.dominio_id = d.id
-- So dominios que imitam uma marca: o link oficial do banco no rodape do e-mail nao entra.
WHERE d.marca_id IS NOT NULL
ORDER BY ch.chegou_em DESC;
