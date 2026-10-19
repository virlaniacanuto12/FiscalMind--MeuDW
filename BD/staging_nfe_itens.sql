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
-- CONTROLE DE DUPLICIDADE:
--   id_nfe = posições 7 a 34 da chave de acesso (44 caracteres):
--   CNPJ/CPF (14) + modelo (2) + série (3) + número (9).
--   É calculado pelo próprio PostgreSQL (coluna gerada, PostgreSQL 12+).
--   A UNIQUE (id_nfe, numero_item) impede que o mesmo item da mesma
--   nota entre duas vezes, mesmo que a DAG rode várias vezes.
--   O CHECK ck_staging_chave_formato recusa chaves mal formadas,
--   que gerariam um id_nfe errado.
--
-- Script não destrutivo: não apaga a tabela se ela já existir.
-- Para recriar do zero, rode antes, manualmente:
--   DROP TABLE staging_nfe.tabela_nfe;
-- e recarregue pela DAG a partir dos XMLs em data/inbox.

CREATE SCHEMA IF NOT EXISTS staging_nfe;

CREATE TABLE IF NOT EXISTS staging_nfe.tabela_nfe (
    -- Nota
    chave_nfe               TEXT NOT NULL,   -- Id da tag infNFe, sem o prefixo "NFe"
    id_nfe                  TEXT GENERATED ALWAYS AS
                                (substring(chave_nfe FROM 7 FOR 28)) STORED,
                                             -- CNPJ/CPF + modelo + série + número
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

    -- Formato da chave: 44 caracteres, sem prefixo "NFe".
    -- cUF + AAMM (6 dígitos) + CNPJ (12 alfanuméricos + 2 dígitos)
    -- + modelo, série, número, tpEmis, cNF e DV (26 dígitos).
    -- Aceita o CNPJ alfanumérico. Garante que id_nfe seja
    -- extraído das posições corretas.
    CONSTRAINT ck_staging_chave_formato
        CHECK (chave_nfe ~ '^[0-9]{6}[0-9A-Z]{12}[0-9]{26}$'),

    -- Uma nota (id_nfe) + item só pode existir uma vez
    CONSTRAINT uq_staging_id_nfe_item
        UNIQUE (id_nfe, numero_item)
);

CREATE INDEX IF NOT EXISTS ix_staging_emitente_documento
    ON staging_nfe.tabela_nfe (emitente_documento);
