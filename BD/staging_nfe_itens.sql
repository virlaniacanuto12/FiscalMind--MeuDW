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
-- UNICIDADE (garantida pelo banco, não só pela DAG):
--   1. chave_nfe (44) + numero_item: o mesmo item da mesma chave
--      nunca entra duas vezes.
--   2. id_nfe (28)   + numero_item: a mesma nota (CNPJ + modelo +
--      série + número) nunca entra com duas chaves de 44 diferentes.
--
--   id_nfe = posições 7 a 34 da chave de 44:
--     CNPJ/CPF (14) + modelo (2) + série (3) + número (9)
--   É calculado pelo próprio PostgreSQL (coluna gerada) e não pode
--   ser informado no INSERT.
--
-- Requer PostgreSQL 12 ou superior (coluna gerada).
--
-- Script idempotente: pode ser executado várias vezes sem apagar
-- dados. Para recriar a tabela do zero, apague-a manualmente antes
-- (DROP TABLE staging_nfe.tabela_nfe;) e recarregue pela DAG a
-- partir dos XMLs em data/inbox.
--
-- VERIFICAÇÃO: o CREATE TABLE IF NOT EXISTS não altera uma tabela
-- que já existe. Por isso o bloco no final deste arquivo confere a
-- estrutura (colunas, tipos, coluna gerada e constraints) e PARA COM
-- ERRO, listando as diferenças, se a tabela existente estiver em
-- outra versão. Executar este arquivo de novo também serve só para
-- conferir a estrutura.
--
-- IMPLANTAÇÃO EM BANCO QUE JÁ TEM A STAGING ANTIGA (uma única vez,
-- manualmente; a staging é recarregada a partir dos XMLs):
--   1. SELECT count(*) AS itens, count(DISTINCT chave_nfe) AS notas
--        FROM staging_nfe.tabela_nfe;                   -- anotar
--   2. CREATE TABLE staging_nfe.tabela_nfe_backup AS
--        SELECT * FROM staging_nfe.tabela_nfe;          -- backup
--   3. DROP TABLE staging_nfe.tabela_nfe;
--   4. Executar este arquivo.
--   5. Esvaziar data/processed e data/failed e executar a
--      dag_extrator_nfe; repetir a contagem do passo 1 (deve ser
--      igual ou maior).
--   6. Conferido o resultado: DROP TABLE staging_nfe.tabela_nfe_backup;

CREATE SCHEMA IF NOT EXISTS staging_nfe;

CREATE TABLE IF NOT EXISTS staging_nfe.tabela_nfe (
    -- Nota
    chave_nfe               TEXT NOT NULL,   -- Id da tag infNFe, sem o prefixo "NFe"
    id_nfe                  TEXT GENERATED ALWAYS AS
                                (substring(chave_nfe FROM 7 FOR 28)) STORED,
                                             -- CNPJ + modelo + série + número
    numero_nota             TEXT,            -- ide/nNF
    serie                   TEXT,            -- ide/serie
    data_emissao            TIMESTAMPTZ,     -- ide/dhEmi
    arquivo_origem          TEXT,            -- nome do arquivo XML lido
    modelo                  TEXT,            -- ide/mod (55 = NF-e)
    tp_nf                   TEXT,            -- ide/tpNF (0 = entrada, 1 = saída, visão do emitente)
    fin_nfe                 TEXT,            -- ide/finNFe (1 = normal, 2 = complementar, 3 = ajuste, 4 = devolução)
    natureza_operacao       TEXT,            -- ide/natOp
    notas_referenciadas     TEXT[],          -- ide/NFref/refNFe (uma nota pode referenciar várias)
    valor_total_nota        NUMERIC,         -- total/ICMSTot/vNF (repetido em cada item)
    qtd_itens_nota          INTEGER,         -- quantidade de det da nota (conferência de carga completa)

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
    codigo_barras_tributavel   TEXT,          -- prod/cEANTrib
    unidade_tributavel         TEXT,          -- prod/uTrib
    quantidade_tributavel      NUMERIC,       -- prod/qTrib
    valor_unitario_tributavel  NUMERIC,       -- prod/vUnTrib
    origem_mercadoria          TEXT,          -- imposto/ICMS/*/orig

    -- Compras: valores e tributos do item
    valor_frete_item           NUMERIC,       -- prod/vFrete
    valor_seguro_item          NUMERIC,       -- prod/vSeg
    valor_outras_despesas_item NUMERIC,       -- prod/vOutro
    valor_icms_item            NUMERIC,       -- imposto/ICMS/*/vICMS
    valor_icms_st_item         NUMERIC,       -- imposto/ICMS/*/vICMSST
    valor_ipi_item             NUMERIC,       -- imposto/IPI/IPITrib/vIPI
    valor_pis_item             NUMERIC,       -- imposto/PIS/*/vPIS
    valor_cofins_item          NUMERIC,       -- imposto/COFINS/*/vCOFINS

    -- Controle
    data_carga              TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Formato da chave: 44 caracteres, sem prefixo "NFe".
    -- cUF + AAMM (6 dígitos) + CNPJ (12 alfanuméricos + 2 dígitos)
    -- + modelo, série, número, tpEmis, cNF e DV (26 dígitos).
    -- Aceita o CNPJ alfanumérico. Sem esta regra, uma chave mal
    -- formada geraria um id_nfe errado.
    CONSTRAINT ck_staging_chave_formato
        CHECK (chave_nfe ~ '^[0-9]{6}[0-9A-Z]{12}[0-9]{26}$'),

    CONSTRAINT ck_staging_numero_item
        CHECK (numero_item > 0),

    -- Unicidade pela chave de 44
    CONSTRAINT uq_staging_nota_item
        UNIQUE (chave_nfe, numero_item),

    -- Unicidade pelos 28 caracteres. Também serve de índice para
    -- a consulta WHERE id_nfe = ... (id_nfe é a primeira coluna),
    -- por isso não é preciso um índice separado em id_nfe.
    CONSTRAINT uq_staging_id_nfe_item
        UNIQUE (id_nfe, numero_item)
);

-- Usado pela dag_dim_fornecedor
CREATE INDEX IF NOT EXISTS ix_staging_emitente_documento
    ON staging_nfe.tabela_nfe (emitente_documento);

-- ============================================================
-- VERIFICAÇÃO DA ESTRUTURA
-- ============================================================
-- Confere tipo, NOT NULL, coluna gerada, constraints e índice, e
-- para com erro listando cada divergência. Colunas a mais apenas
-- geram aviso.
DO $verificacao$
DECLARE
    problemas TEXT[] := '{}';
    r RECORD;
BEGIN
    IF to_regclass('staging_nfe.tabela_nfe') IS NULL THEN
        RAISE EXCEPTION 'staging_nfe.tabela_nfe não existe';
    END IF;

    -- Colunas esperadas: nome, tipo (udt_name), NOT NULL
    FOR r IN
        WITH esperado(coluna, tipo, obrigatoria) AS (VALUES
            ('chave_nfe','text',true), ('id_nfe','text',false),
            ('numero_nota','text',false), ('serie','text',false),
            ('data_emissao','timestamptz',false), ('arquivo_origem','text',false),
            ('modelo','text',false), ('tp_nf','text',false), ('fin_nfe','text',false),
            ('natureza_operacao','text',false), ('notas_referenciadas','_text',false),
            ('valor_total_nota','numeric',false), ('qtd_itens_nota','int4',false),
            ('emitente_documento','text',true), ('emitente_nome','text',false),
            ('emitente_nome_fantasia','text',false), ('emitente_ie','text',false),
            ('emitente_crt','text',false), ('emitente_cod_municipio','text',false),
            ('emitente_municipio','text',false), ('emitente_uf','text',false),
            ('emitente_bairro','text',false),
            ('destinatario_documento','text',false), ('destinatario_nome','text',false),
            ('numero_item','int4',true), ('codigo_produto','text',false),
            ('descricao_produto','text',false), ('ncm','text',false), ('cest','text',false),
            ('codigo_barras','text',false), ('cfop','text',false),
            ('unidade_comercial','text',false), ('quantidade','numeric',false),
            ('valor_unitario','numeric',false), ('valor_produto','numeric',false),
            ('valor_desconto','numeric',false),
            ('codigo_barras_tributavel','text',false), ('unidade_tributavel','text',false),
            ('quantidade_tributavel','numeric',false),
            ('valor_unitario_tributavel','numeric',false),
            ('origem_mercadoria','text',false),
            ('valor_frete_item','numeric',false), ('valor_seguro_item','numeric',false),
            ('valor_outras_despesas_item','numeric',false),
            ('valor_icms_item','numeric',false), ('valor_icms_st_item','numeric',false),
            ('valor_ipi_item','numeric',false), ('valor_pis_item','numeric',false),
            ('valor_cofins_item','numeric',false),
            ('data_carga','timestamptz',true)
        )
        SELECT e.coluna, e.tipo, e.obrigatoria, c.udt_name, c.is_nullable
        FROM esperado e
        LEFT JOIN information_schema.columns c
               ON c.table_schema = 'staging_nfe' AND c.table_name = 'tabela_nfe'
              AND c.column_name = e.coluna
    LOOP
        IF r.udt_name IS NULL THEN
            problemas := problemas || format('coluna ausente: %s', r.coluna);
        ELSIF r.udt_name <> r.tipo THEN
            problemas := problemas || format('coluna %s com tipo %s (esperado %s)',
                                             r.coluna, r.udt_name, r.tipo);
        ELSIF r.obrigatoria AND r.is_nullable <> 'NO' THEN
            problemas := problemas || format('coluna %s deveria ser NOT NULL', r.coluna);
        END IF;
    END LOOP;

    -- id_nfe deve ser gerada a partir das posições 7 a 34 da chave
    -- (o texto da expressão varia conforme a versão do PostgreSQL)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'staging_nfe' AND table_name = 'tabela_nfe'
          AND column_name = 'id_nfe' AND is_generated = 'ALWAYS'
          AND lower(regexp_replace(generation_expression, '[^a-zA-Z0-9_]', '', 'g'))
              IN ('substringchave_nfefrom7for28', 'substringchave_nfe728')
    ) THEN
        problemas := problemas || 'id_nfe não é a coluna gerada substring(chave_nfe FROM 7 FOR 28)'::text;
    END IF;

    -- data_carga com DEFAULT now()
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'staging_nfe' AND table_name = 'tabela_nfe'
          AND column_name = 'data_carga' AND column_default ILIKE '%now()%'
    ) THEN
        problemas := problemas || 'data_carga sem DEFAULT now()'::text;
    END IF;

    -- Constraints: nome e definição
    FOR r IN
        WITH esperado(nome, definicao) AS (VALUES
            ('ck_staging_chave_formato', 'checkchave_nfe~''^[0-9]{6}[0-9a-z]{12}[0-9]{26}$'''),
            ('ck_staging_numero_item',   'checknumero_item>0'),
            ('uq_staging_nota_item',     'uniquechave_nfe,numero_item'),
            ('uq_staging_id_nfe_item',   'uniqueid_nfe,numero_item')
        )
        SELECT e.nome, e.definicao,
               lower(regexp_replace(replace(pg_get_constraintdef(c.oid), '::text', ''),
                                    '[[:space:]()]', '', 'g')) AS atual
        FROM esperado e
        LEFT JOIN pg_constraint c
               ON c.conrelid = 'staging_nfe.tabela_nfe'::regclass AND c.conname = e.nome
    LOOP
        IF r.atual IS NULL THEN
            problemas := problemas || format('constraint ausente: %s', r.nome);
        ELSIF r.atual <> r.definicao THEN
            problemas := problemas || format('constraint %s com definição diferente: %s',
                                             r.nome, r.atual);
        END IF;
    END LOOP;

    -- Índice usado pela dag_dim_fornecedor
    IF to_regclass('staging_nfe.ix_staging_emitente_documento') IS NULL THEN
        problemas := problemas || 'índice ausente: ix_staging_emitente_documento'::text;
    END IF;

    -- Colunas a mais: só aviso
    FOR r IN
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'staging_nfe' AND table_name = 'tabela_nfe'
          AND column_name NOT IN (
            'chave_nfe','id_nfe','numero_nota','serie','data_emissao','arquivo_origem',
            'modelo','tp_nf','fin_nfe','natureza_operacao','notas_referenciadas',
            'valor_total_nota','qtd_itens_nota','emitente_documento','emitente_nome',
            'emitente_nome_fantasia','emitente_ie','emitente_crt','emitente_cod_municipio',
            'emitente_municipio','emitente_uf','emitente_bairro','destinatario_documento',
            'destinatario_nome','numero_item','codigo_produto','descricao_produto','ncm',
            'cest','codigo_barras','cfop','unidade_comercial','quantidade','valor_unitario',
            'valor_produto','valor_desconto','codigo_barras_tributavel','unidade_tributavel',
            'quantidade_tributavel','valor_unitario_tributavel','origem_mercadoria',
            'valor_frete_item','valor_seguro_item','valor_outras_despesas_item',
            'valor_icms_item','valor_icms_st_item','valor_ipi_item','valor_pis_item',
            'valor_cofins_item','data_carga')
    LOOP
        RAISE WARNING 'coluna não prevista na staging (mantida): %', r.column_name;
    END LOOP;

    IF array_length(problemas, 1) > 0 THEN
        RAISE EXCEPTION E'Estrutura de staging_nfe.tabela_nfe divergente (% problema(s)):\n- %',
            array_length(problemas, 1), array_to_string(problemas, E'\n- ');
    END IF;

    RAISE NOTICE 'staging_nfe.tabela_nfe: estrutura conferida, sem divergências.';
END
$verificacao$;
