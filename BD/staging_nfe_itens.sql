-- ============================================================
-- FISCALMIND - STAGING DE NF-e (UMA LINHA POR ITEM)
-- ============================================================
-- Estrutura usada pela DAG dag_extrator_nfe.
--
-- Grão: 1 linha = 1 item (tag <det>) de 1 nota fiscal.
-- Os dados da nota, do emitente e do destinatário se repetem
-- em cada item. As dimensões são montadas a partir desta tabela
-- (ex.: dim_fornecedor faz um DISTINCT por emitente_documento).
--
-- A staging guarda o dado bruto do XML, sem regra de negócio.
-- Novas colunas podem ser acrescentadas com ALTER TABLE ... ADD COLUMN
-- conforme o projeto precisar; o grão (nota + item) não deve mudar.
--
-- Duplicatas (parcelas/vencimentos) têm outro grão e devem ir
-- para uma staging própria, nunca para esta tabela.
--
-- ATENÇÃO: substitui a versão anterior (uma linha por emitente).
-- A staging pode ser recriada a qualquer momento, pois é
-- recarregada a partir dos XMLs em data/inbox.

CREATE SCHEMA IF NOT EXISTS staging_nfe;

DROP TABLE IF EXISTS staging_nfe.tabela_nfe;

CREATE TABLE staging_nfe.tabela_nfe (
    -- Nota
    chave_nfe               TEXT NOT NULL,   -- Id da tag infNFe, sem o prefixo "NFe"
    numero_nota             TEXT,            -- ide/nNF
    serie                   TEXT,            -- ide/serie
    data_emissao            TIMESTAMPTZ,     -- ide/dhEmi
    arquivo_origem          TEXT,            -- nome do arquivo XML lido

    -- Emitente (fornecedor nas notas de entrada)
    emitente_documento      TEXT NOT NULL,   -- CNPJ ou CPF
    emitente_nome           TEXT,
    emitente_nome_fantasia  TEXT,
    emitente_ie             TEXT,
    emitente_crt            TEXT,            -- 1 = Simples Nacional, 2 = Simples (excesso), 3 = Regime Normal
    emitente_cod_municipio  TEXT,            -- código IBGE
    emitente_municipio      TEXT,
    emitente_uf             TEXT,
    emitente_bairro         TEXT,

    -- Destinatário
    destinatario_documento  TEXT,
    destinatario_nome       TEXT,

    -- Item
    numero_item             INTEGER NOT NULL, -- atributo nItem da tag det
    codigo_produto          TEXT,             -- prod/cProd
    descricao_produto       TEXT,             -- prod/xProd
    ncm                     TEXT,
    cest                    TEXT,
    codigo_barras           TEXT,             -- prod/cEAN
    cfop                    TEXT,
    unidade_comercial       TEXT,             -- prod/uCom
    quantidade              NUMERIC,          -- prod/qCom
    valor_unitario          NUMERIC,          -- prod/vUnCom
    valor_produto           NUMERIC,          -- prod/vProd
    valor_desconto          NUMERIC,          -- prod/vDesc

    -- Controle
    data_carga              TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_staging_nota_item
        UNIQUE (chave_nfe, numero_item)
);

CREATE INDEX IF NOT EXISTS ix_staging_emitente_documento
    ON staging_nfe.tabela_nfe (emitente_documento);
