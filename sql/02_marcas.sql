-- Marcas monitoradas. Comecar pequeno: um banco, bem feito, antes de escalar.
-- "bradesco" sozinho e o TLD proprio do banco (ex.: banco.bradesco).
INSERT INTO marca (nome, dominios_oficiais, palavras_chave) VALUES
    ('Bradesco',
     ARRAY['bradesco.com.br', 'bradesco', 'bradescoseguros.com.br', 'next.me'],
     ARRAY['bradesco', 'bradesc0', 'bradescco', 'bradesko', 'bradesconet']);
