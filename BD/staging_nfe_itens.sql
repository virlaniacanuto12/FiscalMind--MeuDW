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
-- IDENTIFICAÇÃO DA LINHA:
--   if_nfe (bigserial) é a chave primária: um número sequencial
--   gerado pelo banco para cada linha (item). Não identifica a nota.
--
-- CONTROLE DE DUPLICIDADE:
--   A UNIQUE uq_staging_nfe_item usa os campos originais do XML:
--   emitente_documento (CNPJ/CPF) + modelo + série + número + item.
--   Ela impede que o mesmo item da mesma nota entre duas vezes,
--   mesmo que a DAG rode várias vezes (ON CONFLICT DO NOTHING).
--   As 5 colunas são NOT NULL, porque NULL escapa da UNIQUE.
--
--   id_nfe (posições 7 a 34 da chave de acesso) continua na tabela
--   como coluna gerada, mas NÃO faz mais parte da regra de unicidade.
--   O CHECK ck_staging_chave_formato recusa chaves mal formadas.
--
-- Script não destrutivo: não apaga a tabela se ela já existir.
-- ATENÇÃO: por causa do IF NOT EXISTS, rodar este script sobre uma
-- tabela antiga NÃO a atualiza (e não dá erro). Para recriar do zero,
-- rode antes, manualmente:
--   DROP TABLE staging_nfe.tabela_nfe;
-- e recarregue pela DAG a partir dos XMLs em data/inbox.
 
CREATE SCHEMA IF NOT EXISTS staging_nfe;
 
CREATE TABLE IF NOT EXISTS staging_nfe.tabela_nfe (
    -- Identificação da linha
    id_nfe                  BIGSERIAL,       -- sequencial gerado pelo banco (1 por item)
 
    -- Nota
    chave_nfe               TEXT NOT NULL,   -- Id da tag infNFe, sem o prefixo "NFe"
    modelo                  SMALLINT NOT NULL, -- ide/mod (55 = NF-e, 65 = NFC-e)
    serie                   SMALLINT NOT NULL, -- ide/serie (0 a 999)
    numero_nota             INTEGER  NOT NULL, -- ide/nNF (1 a 999.999.999)
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
    valor_desconto          NUMERIC NOT NULL DEFAULT 0, -- prod/vDesc (0 quando a nota não tem desconto)
 
    -- Controle
    data_carga              TIMESTAMPTZ NOT NULL DEFAULT now(),
 
    CONSTRAINT pk_nfe PRIMARY KEY (id_nfe),
 
    -- Formato da chave: 44 caracteres, sem prefixo "NFe".
    -- cUF + AAMM (6 dígitos) + CNPJ (12 alfanuméricos + 2 dígitos)
    -- + modelo, série, número, tpEmis, cNF e DV (26 dígitos).
    -- Aceita o CNPJ alfanumérico. Garante que id_nfe seja
    -- extraído das posições corretas.
    CONSTRAINT ck_staging_chave_formato
        CHECK (chave_nfe ~ '^[0-9]{6}[0-9A-Z]{12}[0-9]{26}$'),
 
    -- Uma nota (emitente + modelo + série + número) + item só pode existir uma vez
    CONSTRAINT uq_staging_nfe_item
        UNIQUE (emitente_documento, modelo, serie, numero_nota, numero_item)
);
 
CREATE INDEX IF NOT EXISTS ix_staging_emitente_documento
    ON staging_nfe.tabela_nfe (emitente_documento);
 