-- Ajuste da dw.dim_produto em banco que já tem a tabela (executar uma vez).
-- A dimensão ainda não foi carregada; se tiver linhas, rode antes:
--   TRUNCATE dw.dim_produto;   (falha se a fato_compra já referenciar produtos)
ALTER TABLE dw.dim_produto
    ADD COLUMN documento_fornecedor character varying(20) NOT NULL;
ALTER TABLE dw.dim_produto
    DROP CONSTRAINT uq_dim_produto_codigo;
ALTER TABLE dw.dim_produto
    ADD CONSTRAINT uq_dim_produto_fornecedor_codigo
    UNIQUE (documento_fornecedor, codigo_produto);
 