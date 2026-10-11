
-- ============================================================
-- FISCALMIND - STAGING DE EMITENTES
-- ============================================================
-- Estrutura atual utilizada pela DAG dag_extrator_nfe.
-- Um registro por documento de emitente.
-- Os emitentes ainda não foram classificados comercialmente.

CREATE SCHEMA IF NOT EXISTS staging_nfe;

CREATE TABLE IF NOT EXISTS staging_nfe.tabela_nfe (
    arquivo_origem TEXT,
    emitente_documento TEXT NOT NULL,
    emitente_nome TEXT,
    emitente_nome_fantasia TEXT,
    emitente_municipio TEXT,
    emitente_uf TEXT,
    emitente_bairro TEXT,

    CONSTRAINT uq_staging_emitente_documento
        UNIQUE (emitente_documento)
);
