# Dicionário de colunas — FiscalMind

Este documento explica as **164 colunas** encontradas na tabela gerada por `etl/extrair_tabela.py` com os 194 XMLs examinados (2.156 linhas de itens). O CSV anexado foi conferido: contém 164 colunas e 2.156 linhas de itens, referentes a 194 chaves distintas. É a documentação dessa extração, e não uma lista de todos os campos possíveis da NF-e.

## Como ler a tabela

- **Uma linha da tabela corresponde a um item (`det`) de uma nota.** Informações da nota e das partes se repetem em seus itens. Não contar linhas como quantidade de notas.
- **Os totais `total_nota_` pertencem à nota inteira e se repetem em seus itens.** Não somar essas colunas linha a linha; considerar uma única ocorrência por nota, identificada por `chave_nfe`.
- **Caminho no XML** mostra onde o campo está. `/` significa entrar em um grupo; `@` indica um atributo. O prefixo `nfeProc/`, quando existe envolvendo `NFe`, foi omitido nos caminhos da nota.
- **Coluna na tabela** é o nome usado no CSV. As colunas fiscais preservam o caminho, trocando `/` por `_`, para distinguir campos com a mesma tag em grupos diferentes.
- **Vazio não é zero.** Vazio significa que o campo não foi encontrado para aquele item; `0,00` significa zero informado. Grupos fiscais alternativos geram muitas células vazias.
- O CSV usa ponto e vírgula (`;`) para separar colunas e vírgula como separador decimal, preservando os dígitos e as casas decimais do XML. `18,00` em uma alíquota significa **18%**; `18,00` em um valor monetário significa **R$ 18,00**. Na planilha, usar uma localidade compatível, como Brasil. A formatação visual depende da importação.
- Chaves, documentos, GTINs, NCMs, CFOPs e códigos fiscais devem ser tratados como **texto** para preservar zeros e evitar notação científica.
- Os valores são **informados no XML**: o extrator não calcula impostos, margem de lucro ou custo completo. XML pseudonimizado não recupera a identidade real do produto/empresa.
- Emitente e destinatário ainda não são automaticamente fornecedor e cliente do FiscalMind. Isso depende de identificar a empresa analisada e a natureza da operação.
- O relatório de leitura registra ocorrências da execução; este dicionário explica as colunas. São documentos com funções diferentes.

## 1. Identificação da nota e protocolo

| Caminho no XML / origem | Coluna na tabela | Significado | Como interpretar |
|---|---|---|---|
| `Não vem de uma tag: caminho do arquivo` | `arquivo_origem` | Arquivo XML que originou a linha. | Caminho relativo à pasta de entrada. O nome do arquivo pode diferir da chave interna após a pseudonimização. |
| `NFe/infNFe/@Id` | `chave_nfe` | Chave de acesso encontrada dentro do XML. | Texto de 44 dígitos; o extrator remove o prefixo NFe. Não utiliza o nome do arquivo para preencher esta coluna. |
| `NFe/infNFe/ide/nNF` | `numero_nota` | Número da nota fiscal. | Identificador; pode se repetir entre emitentes ou séries. |
| `NFe/infNFe/ide/serie` | `serie` | Série da nota fiscal. | Código; não é quantidade. |
| `NFe/infNFe/ide/mod` | `modelo` | Modelo do documento fiscal. | 55 = NF-e; 65 = NFC-e. |
| `NFe/infNFe/ide/dhEmi (ou dEmi em leiautes antigos)` | `data_hora_emissao` | Data e hora de emissão, conforme o XML. | Preserva o texto original e o fuso, quando presentes. A alternativa dEmi contém somente a data. |
| `Derivada de dhEmi/dEmi pelo extrator` | `data_emissao` | Data de emissão sem o horário. | Primeiros 10 caracteres da emissão: AAAA-MM-DD. Não há conversão de fuso horário. |
| `NFe/infNFe/ide/natOp` | `natureza_operacao` | Descrição da natureza da operação. | Texto informado pelo emitente; não substitui a classificação pelo CFOP. |
| `NFe/infNFe/ide/tpNF` | `tipo_nfe` | Entrada ou saída sob a perspectiva do emitente. | 0 = entrada; 1 = saída. Uma saída do fornecedor pode ser uma compra para a empresa analisada. |
| `NFe/infNFe/ide/finNFe` | `finalidade_nfe` | Finalidade de emissão da nota. | 1 = normal; 2 = complementar; 3 = ajuste; 4 = devolução/retorno; 5 = crédito; 6 = débito. Não tratar todas como venda normal. |
| `NFe/infNFe/ide/idDest` | `destino_operacao` | Abrangência da operação. | 1 = interna; 2 = interestadual; 3 = exterior. |
| `NFe/infNFe/ide/tpAmb` | `ambiente` | Ambiente de emissão. | 1 = produção; 2 = homologação (testes). Não significa que a nota foi validada pelo extrator. |
| `nfeProc/protNFe/infProt/cStat` | `status_protocolo` | Código do resultado registrado no protocolo. | 100 indica autorização de uso. Pode ficar vazio sem protocolo. Não informa, sozinho, cancelamentos posteriores nem valida a autenticidade do XML. |

## 2. Emitente e destinatário

| Caminho no XML / origem | Coluna na tabela | Significado | Como interpretar |
|---|---|---|---|
| `Derivada da tag preenchida em NFe/infNFe/emit/` | `emitente_tipo_documento` | Tipo do identificador encontrado. | CNPJ ou CPF, conforme o campo disponível. |
| `NFe/infNFe/emit/CNPJ ou CPF` | `emitente_documento` | Identificador do emitente. | Tratar como texto para preservar zeros iniciais. No ambiente acadêmico, pode estar pseudonimizado. |
| `NFe/infNFe/emit/xNome` | `emitente_nome` | Nome/razão social do emitente. | Texto informado no XML; pode estar pseudonimizado. |
| `NFe/infNFe/emit/xFant` | `emitente_nome_fantasia` | Nome fantasia do emitente. | Campo opcional; vazio se não informado. |
| `NFe/infNFe/emit/IE` | `emitente_ie` | Inscrição estadual do emitente. | Identificador textual; ausência não equivale a zero. |
| `NFe/infNFe/emit/CRT` | `emitente_crt` | Código do regime tributário do emitente. | 1 = Simples Nacional; 2 = Simples com excesso de sublimite; 3 = regime normal; 4 = Simples Nacional/MEI. |
| `NFe/infNFe/emit/enderEmit/cMun` | `emitente_codigo_municipio` | Código do município. | Código cadastral, geralmente IBGE; não é medida numérica. |
| `NFe/infNFe/emit/enderEmit/xMun` | `emitente_municipio` | Nome do município. | Texto do endereço. |
| `NFe/infNFe/emit/enderEmit/UF` | `emitente_uf` | Unidade federativa. | Sigla como SP ou MG; EX pode indicar exterior. |
| `NFe/infNFe/emit/enderEmit/xBairro` | `emitente_bairro` | Bairro do endereço. | Texto; pode estar pseudonimizado. |
| `Derivada da tag preenchida em NFe/infNFe/dest/` | `destinatario_tipo_documento` | Tipo do identificador encontrado. | CNPJ, CPF ou idEstrangeiro, conforme o campo disponível. |
| `NFe/infNFe/dest/CNPJ ou CPF ou idEstrangeiro` | `destinatario_documento` | Identificador do destinatário. | Tratar como texto para preservar zeros iniciais. No ambiente acadêmico, pode estar pseudonimizado. |
| `NFe/infNFe/dest/xNome` | `destinatario_nome` | Nome/razão social do destinatário. | Texto informado no XML; pode estar pseudonimizado. |
| `Sem tag padrão correspondente em NFe/infNFe/dest` | `destinatario_nome_fantasia` | Coluna criada pelo extrator, sem origem no grupo padrão dest. | O código procura dest/xFant, mas essa tag não pertence ao grupo padrão. Vazia nos arquivos examinados; não inferir o nome fantasia. |
| `NFe/infNFe/dest/IE` | `destinatario_ie` | Inscrição estadual do destinatário. | Identificador textual; ausência não equivale a zero. |
| `Sem tag padrão correspondente em NFe/infNFe/dest` | `destinatario_crt` | Coluna criada pelo extrator, sem origem no grupo padrão dest. | O código procura dest/CRT, mas essa tag não pertence ao grupo padrão. Vazia nos arquivos examinados; não inferir o regime tributário. |
| `NFe/infNFe/dest/enderDest/cMun` | `destinatario_codigo_municipio` | Código do município. | Código cadastral, geralmente IBGE; não é medida numérica. |
| `NFe/infNFe/dest/enderDest/xMun` | `destinatario_municipio` | Nome do município. | Texto do endereço. |
| `NFe/infNFe/dest/enderDest/UF` | `destinatario_uf` | Unidade federativa. | Sigla como SP ou MG; EX pode indicar exterior. |
| `NFe/infNFe/dest/enderDest/xBairro` | `destinatario_bairro` | Bairro do endereço. | Texto; pode estar pseudonimizado. |

## 3. Item e produto

| Caminho no XML / origem | Coluna na tabela | Significado | Como interpretar |
|---|---|---|---|
| `NFe/infNFe/det/@nItem` | `numero_item` | Número do item dentro da nota. | Atributo do grupo det. Identifica o item em conjunto com a nota; não é código do produto. |
| `NFe/infNFe/det/prod/cProd` | `codigo_produto` | Código de produto usado pelo emitente. | Texto. Não é um identificador universal entre empresas. |
| `NFe/infNFe/det/prod/xProd` | `descricao_produto` | Descrição do produto/serviço. | Texto do XML; não representa uma categoria padronizada. |
| `NFe/infNFe/det/prod/NCM` | `ncm` | Classificação fiscal da mercadoria. | Código textual de até 8 dígitos. Se pseudonimizado, não permite recuperar a categoria fiscal real. |
| `NFe/infNFe/det/prod/CEST` | `cest` | Código Especificador da Substituição Tributária. | Código textual de 7 dígitos, quando informado; preservar zeros. |
| `NFe/infNFe/det/prod/CFOP` | `cfop` | Código Fiscal de Operações e Prestações. | Código de 4 dígitos. Descreve a operação do item; não é alíquota. Sua interpretação depende da tabela oficial de CFOP. |
| `NFe/infNFe/det/prod/cEAN` | `gtin_comercial` | GTIN referente à unidade comercial. | Texto; pode conter SEM GTIN. Não considerar esse literal um identificador de produto. |
| `NFe/infNFe/det/prod/uCom` | `unidade_comercial` | Unidade usada na comercialização. | Ex.: UN, KG ou CX. Conferir unidades antes de comparar preços e quantidades. |
| `NFe/infNFe/det/prod/qCom` | `quantidade_comercial` | Quantidade comercial do item. | Número decimal expresso em uCom; não é quantidade de notas. |
| `NFe/infNFe/det/prod/vUnCom` | `valor_unitario_comercial` | Preço unitário na unidade comercial. | R$/uCom. Preserva as casas decimais do XML; ainda não representa custo completo ou margem. |
| `NFe/infNFe/det/prod/vProd` | `valor_produto` | Valor bruto do produto/serviço neste item. | R$. Não é o total da nota nem um valor líquido após descontos e tributos. |
| `NFe/infNFe/det/prod/cEANTrib` | `gtin_tributavel` | GTIN referente à unidade tributável. | Pode diferir do GTIN comercial; pode conter SEM GTIN. |
| `NFe/infNFe/det/prod/uTrib` | `unidade_tributavel` | Unidade utilizada para tributação. | Pode diferir da unidade comercial; não presumir equivalência automática. |
| `NFe/infNFe/det/prod/qTrib` | `quantidade_tributavel` | Quantidade expressa na unidade tributável. | Número decimal em uTrib; pode diferir de qCom. |
| `NFe/infNFe/det/prod/vUnTrib` | `valor_unitario_tributavel` | Valor unitário na unidade tributável. | R$/uTrib; pode diferir de vUnCom por causa da unidade. |
| `NFe/infNFe/det/prod/vDesc` | `valor_desconto` | Desconto atribuído ao item. | R$, não percentual. Vazio quando a tag não existe; 0,00 é zero explicitamente informado. |
| `NFe/infNFe/det/prod/vOutro` | `valor_outros` | Outras despesas acessórias atribuídas ao item. | R$. Preservado do XML, sem classificação adicional. |
| `NFe/infNFe/det/prod/indTot` | `compoe_total_nota` | Indica se vProd deste item participa da totalização de produtos da nota. | 1 = participa; 0 = não participa. É um código, não R$ 1. Não determina sozinho o total final vNF. |

## 4. Tributos do item

Cada caminho abaixo começa em `NFe/infNFe/det`. Os grupos `ICMS00`, `ICMS10`, `ICMS60`, `ICMSSN101` etc. representam tratamentos fiscais distintos. Não são tabelas adicionais: são origens de colunas na mesma tabela de itens.

| Caminho no XML / origem | Coluna na tabela | Significado | Como interpretar |
|---|---|---|---|
| `NFe/infNFe/det/impostoDevol/IPI/vIPIDevol` | `impostoDevol_IPI_vIPIDevol` | Valor do IPI devolvido. | R$; não confundir com o IPI destacado em imposto/IPI. |
| `NFe/infNFe/det/impostoDevol/pDevol` | `impostoDevol_pDevol` | Percentual de mercadoria devolvida. | Percentual; não é desconto comercial. |
| `NFe/infNFe/det/imposto/COFINS/COFINSAliq/CST` | `imposto_COFINS_COFINSAliq_CST` | Código da situação tributária de COFINS. | Código textual; preservar zeros e interpretar dentro deste tributo e grupo. Consulte os códigos encontrados abaixo. |
| `NFe/infNFe/det/imposto/COFINS/COFINSAliq/pCOFINS` | `imposto_COFINS_COFINSAliq_pCOFINS` | Alíquota de COFINS. | Percentual, não R$. |
| `NFe/infNFe/det/imposto/COFINS/COFINSAliq/vBC` | `imposto_COFINS_COFINSAliq_vBC` | Base de cálculo do tributo neste grupo. | R$. A base pode diferir do valor bruto do produto. |
| `NFe/infNFe/det/imposto/COFINS/COFINSAliq/vCOFINS` | `imposto_COFINS_COFINSAliq_vCOFINS` | Valor de COFINS neste grupo do item. | R$; copiado sem recalcular. |
| `NFe/infNFe/det/imposto/COFINS/COFINSNT/CST` | `imposto_COFINS_COFINSNT_CST` | Código da situação tributária de COFINS. | Código textual; preservar zeros e interpretar dentro deste tributo e grupo. Consulte os códigos encontrados abaixo. |
| `NFe/infNFe/det/imposto/COFINS/COFINSOutr/CST` | `imposto_COFINS_COFINSOutr_CST` | Código da situação tributária de COFINS. | Código textual; preservar zeros e interpretar dentro deste tributo e grupo. Consulte os códigos encontrados abaixo. |
| `NFe/infNFe/det/imposto/COFINS/COFINSOutr/pCOFINS` | `imposto_COFINS_COFINSOutr_pCOFINS` | Alíquota de COFINS. | Percentual, não R$. |
| `NFe/infNFe/det/imposto/COFINS/COFINSOutr/qBCProd` | `imposto_COFINS_COFINSOutr_qBCProd` | Quantidade usada como base para COFINS. | Quantidade para cálculo por unidade; não é uma base em reais. |
| `NFe/infNFe/det/imposto/COFINS/COFINSOutr/vAliqProd` | `imposto_COFINS_COFINSOutr_vAliqProd` | Alíquota em valor por unidade de COFINS. | R$/unidade; não percentual e não preço de venda do produto. |
| `NFe/infNFe/det/imposto/COFINS/COFINSOutr/vBC` | `imposto_COFINS_COFINSOutr_vBC` | Base de cálculo do tributo neste grupo. | R$. A base pode diferir do valor bruto do produto. |
| `NFe/infNFe/det/imposto/COFINS/COFINSOutr/vCOFINS` | `imposto_COFINS_COFINSOutr_vCOFINS` | Valor de COFINS neste grupo do item. | R$; copiado sem recalcular. |
| `NFe/infNFe/det/imposto/IBSCBS/CST` | `imposto_IBSCBS_CST` | Código da situação tributária de IBSCBS. | Código textual; preservar zeros e interpretar dentro deste tributo e grupo. Consulte os códigos encontrados abaixo. |
| `NFe/infNFe/det/imposto/IBSCBS/cClassTrib` | `imposto_IBSCBS_cClassTrib` | Código de classificação tributária do IBS/CBS. | Código textual; consultar tabela oficial vigente. Não confundir com categoria comercial do produto. |
| `NFe/infNFe/det/imposto/IBSCBS/gIBSCBS/gCBS/gDevTrib/vDevTrib` | `imposto_IBSCBS_gIBSCBS_gCBS_gDevTrib_vDevTrib` | Valor de devolução de tributos no componente deste grupo. Componente: CBS. | R$; identificar se o caminho indica CBS, IBS municipal ou IBS estadual. Não é a mesma informação que impostoDevol/IPI. |
| `NFe/infNFe/det/imposto/IBSCBS/gIBSCBS/gCBS/gRed/pAliqEfet` | `imposto_IBSCBS_gIBSCBS_gCBS_gRed_pAliqEfet` | Alíquota efetiva aplicada à base de cálculo do tributo deste grupo. Componente: CBS. | Percentual após os ajustes previstos no grupo de redução. |
| `NFe/infNFe/det/imposto/IBSCBS/gIBSCBS/gCBS/gRed/pRedAliq` | `imposto_IBSCBS_gIBSCBS_gCBS_gRed_pRedAliq` | Percentual de redução da alíquota do tributo deste grupo. Componente: CBS. | Percentual de redução; não é a alíquota final nem desconto do produto. |
| `NFe/infNFe/det/imposto/IBSCBS/gIBSCBS/gCBS/pCBS` | `imposto_IBSCBS_gIBSCBS_gCBS_pCBS` | Alíquota da CBS antes da aplicação de redução indicada no grupo próprio. Componente: CBS. | Percentual; conferir também gRed/pAliqEfet, quando presente. |
| `NFe/infNFe/det/imposto/IBSCBS/gIBSCBS/gCBS/vCBS` | `imposto_IBSCBS_gIBSCBS_gCBS_vCBS` | Valor da CBS. Componente: CBS. | R$; preservado conforme o grupo do item. |
| `NFe/infNFe/det/imposto/IBSCBS/gIBSCBS/gIBSMun/gDevTrib/vDevTrib` | `imposto_IBSCBS_gIBSCBS_gIBSMun_gDevTrib_vDevTrib` | Valor de devolução de tributos no componente deste grupo. Componente: IBS municipal. | R$; identificar se o caminho indica CBS, IBS municipal ou IBS estadual. Não é a mesma informação que impostoDevol/IPI. |
| `NFe/infNFe/det/imposto/IBSCBS/gIBSCBS/gIBSMun/gRed/pAliqEfet` | `imposto_IBSCBS_gIBSCBS_gIBSMun_gRed_pAliqEfet` | Alíquota efetiva aplicada à base de cálculo do tributo deste grupo. Componente: IBS municipal. | Percentual após os ajustes previstos no grupo de redução. |
| `NFe/infNFe/det/imposto/IBSCBS/gIBSCBS/gIBSMun/gRed/pRedAliq` | `imposto_IBSCBS_gIBSCBS_gIBSMun_gRed_pRedAliq` | Percentual de redução da alíquota do tributo deste grupo. Componente: IBS municipal. | Percentual de redução; não é a alíquota final nem desconto do produto. |
| `NFe/infNFe/det/imposto/IBSCBS/gIBSCBS/gIBSMun/pIBSMun` | `imposto_IBSCBS_gIBSCBS_gIBSMun_pIBSMun` | Alíquota do IBS de competência municipal. Componente: IBS municipal. | Percentual; conferir também a redução, quando presente. |
| `NFe/infNFe/det/imposto/IBSCBS/gIBSCBS/gIBSMun/vIBSMun` | `imposto_IBSCBS_gIBSCBS_gIBSMun_vIBSMun` | Valor do IBS de competência municipal. Componente: IBS municipal. | R$; não é o IBS estadual. |
| `NFe/infNFe/det/imposto/IBSCBS/gIBSCBS/gIBSUF/gDevTrib/vDevTrib` | `imposto_IBSCBS_gIBSCBS_gIBSUF_gDevTrib_vDevTrib` | Valor de devolução de tributos no componente deste grupo. Componente: IBS estadual. | R$; identificar se o caminho indica CBS, IBS municipal ou IBS estadual. Não é a mesma informação que impostoDevol/IPI. |
| `NFe/infNFe/det/imposto/IBSCBS/gIBSCBS/gIBSUF/gRed/pAliqEfet` | `imposto_IBSCBS_gIBSCBS_gIBSUF_gRed_pAliqEfet` | Alíquota efetiva aplicada à base de cálculo do tributo deste grupo. Componente: IBS estadual. | Percentual após os ajustes previstos no grupo de redução. |
| `NFe/infNFe/det/imposto/IBSCBS/gIBSCBS/gIBSUF/gRed/pRedAliq` | `imposto_IBSCBS_gIBSCBS_gIBSUF_gRed_pRedAliq` | Percentual de redução da alíquota do tributo deste grupo. Componente: IBS estadual. | Percentual de redução; não é a alíquota final nem desconto do produto. |
| `NFe/infNFe/det/imposto/IBSCBS/gIBSCBS/gIBSUF/pIBSUF` | `imposto_IBSCBS_gIBSCBS_gIBSUF_pIBSUF` | Alíquota do IBS de competência estadual. Componente: IBS estadual. | Percentual; conferir também a redução, quando presente. |
| `NFe/infNFe/det/imposto/IBSCBS/gIBSCBS/gIBSUF/vIBSUF` | `imposto_IBSCBS_gIBSCBS_gIBSUF_vIBSUF` | Valor do IBS de competência estadual. Componente: IBS estadual. | R$; não é o IBS municipal. |
| `NFe/infNFe/det/imposto/IBSCBS/gIBSCBS/vBC` | `imposto_IBSCBS_gIBSCBS_vBC` | Base de cálculo do IBS/CBS do item. | R$. A base pode diferir do valor bruto do produto. |
| `NFe/infNFe/det/imposto/IBSCBS/gIBSCBS/vIBS` | `imposto_IBSCBS_gIBSCBS_vIBS` | Valor do IBS informado para o item. | R$; há campos separados para os componentes estadual e municipal. |
| `NFe/infNFe/det/imposto/ICMS/ICMS00/CST` | `imposto_ICMS_ICMS00_CST` | Código da situação tributária de ICMS. | Código textual; preservar zeros e interpretar dentro deste tributo e grupo. Consulte os códigos encontrados abaixo. |
| `NFe/infNFe/det/imposto/ICMS/ICMS00/modBC` | `imposto_ICMS_ICMS00_modBC` | Modalidade de determinação da base de cálculo do ICMS. | Código; consultar a tabela modBC abaixo. |
| `NFe/infNFe/det/imposto/ICMS/ICMS00/orig` | `imposto_ICMS_ICMS00_orig` | Origem da mercadoria para fins do ICMS. | Código; consultar a tabela de origem abaixo. |
| `NFe/infNFe/det/imposto/ICMS/ICMS00/pICMS` | `imposto_ICMS_ICMS00_pICMS` | Alíquota do ICMS. | Percentual: 18,00 significa 18%. |
| `NFe/infNFe/det/imposto/ICMS/ICMS00/vBC` | `imposto_ICMS_ICMS00_vBC` | Base de cálculo do tributo neste grupo. | R$. A base pode diferir do valor bruto do produto. |
| `NFe/infNFe/det/imposto/ICMS/ICMS00/vICMS` | `imposto_ICMS_ICMS00_vICMS` | Valor do ICMS informado para o item neste grupo. | R$. O extrator copia o valor, sem recalcular. |
| `NFe/infNFe/det/imposto/ICMS/ICMS10/CST` | `imposto_ICMS_ICMS10_CST` | Código da situação tributária de ICMS. | Código textual; preservar zeros e interpretar dentro deste tributo e grupo. Consulte os códigos encontrados abaixo. |
| `NFe/infNFe/det/imposto/ICMS/ICMS10/modBC` | `imposto_ICMS_ICMS10_modBC` | Modalidade de determinação da base de cálculo do ICMS. | Código; consultar a tabela modBC abaixo. |
| `NFe/infNFe/det/imposto/ICMS/ICMS10/modBCST` | `imposto_ICMS_ICMS10_modBCST` | Modalidade de determinação da base de cálculo do ICMS por substituição tributária. | Código; consultar a tabela modBCST abaixo. |
| `NFe/infNFe/det/imposto/ICMS/ICMS10/orig` | `imposto_ICMS_ICMS10_orig` | Origem da mercadoria para fins do ICMS. | Código; consultar a tabela de origem abaixo. |
| `NFe/infNFe/det/imposto/ICMS/ICMS10/pICMS` | `imposto_ICMS_ICMS10_pICMS` | Alíquota do ICMS. | Percentual: 18,00 significa 18%. |
| `NFe/infNFe/det/imposto/ICMS/ICMS10/pICMSST` | `imposto_ICMS_ICMS10_pICMSST` | Alíquota do ICMS por substituição tributária. | Percentual; não é um valor em reais. |
| `NFe/infNFe/det/imposto/ICMS/ICMS10/pMVAST` | `imposto_ICMS_ICMS10_pMVAST` | Margem de valor agregado usada no cálculo do ICMS-ST. | Percentual fiscal; não é a margem de lucro comercial do produto. |
| `NFe/infNFe/det/imposto/ICMS/ICMS10/vBC` | `imposto_ICMS_ICMS10_vBC` | Base de cálculo do tributo neste grupo. | R$. A base pode diferir do valor bruto do produto. |
| `NFe/infNFe/det/imposto/ICMS/ICMS10/vBCST` | `imposto_ICMS_ICMS10_vBCST` | Base de cálculo do ICMS-ST. | R$; diferente da base do ICMS próprio. |
| `NFe/infNFe/det/imposto/ICMS/ICMS10/vICMS` | `imposto_ICMS_ICMS10_vICMS` | Valor do ICMS informado para o item neste grupo. | R$. O extrator copia o valor, sem recalcular. |
| `NFe/infNFe/det/imposto/ICMS/ICMS10/vICMSST` | `imposto_ICMS_ICMS10_vICMSST` | Valor do ICMS por substituição tributária. | R$; não somar indiscriminadamente com ICMS próprio para calcular custo. |
| `NFe/infNFe/det/imposto/ICMS/ICMS60/CST` | `imposto_ICMS_ICMS60_CST` | Código da situação tributária de ICMS. | Código textual; preservar zeros e interpretar dentro deste tributo e grupo. Consulte os códigos encontrados abaixo. |
| `NFe/infNFe/det/imposto/ICMS/ICMS60/orig` | `imposto_ICMS_ICMS60_orig` | Origem da mercadoria para fins do ICMS. | Código; consultar a tabela de origem abaixo. |
| `NFe/infNFe/det/imposto/ICMS/ICMS60/pST` | `imposto_ICMS_ICMS60_pST` | Alíquota suportada pelo consumidor final, no grupo de ICMS retido. | Percentual; não confundir com o valor de ICMS-ST. |
| `NFe/infNFe/det/imposto/ICMS/ICMS60/vBCSTRet` | `imposto_ICMS_ICMS60_vBCSTRet` | Base de cálculo do ICMS-ST retido anteriormente. | R$; refere-se à retenção anterior. |
| `NFe/infNFe/det/imposto/ICMS/ICMS60/vICMSSTRet` | `imposto_ICMS_ICMS60_vICMSSTRet` | Valor do ICMS-ST retido anteriormente. | R$; não representa necessariamente uma nova cobrança nesta nota. |
| `NFe/infNFe/det/imposto/ICMS/ICMS60/vICMSSubstituto` | `imposto_ICMS_ICMS60_vICMSSubstituto` | ICMS próprio do substituto cobrado em operação anterior. | R$; distinto de vICMSSTRet. |
| `NFe/infNFe/det/imposto/ICMS/ICMSSN101/CSOSN` | `imposto_ICMS_ICMSSN101_CSOSN` | Código da situação da operação no Simples Nacional para ICMS. | Código textual; consultar os códigos encontrados abaixo. Não é o CRT da empresa. |
| `NFe/infNFe/det/imposto/ICMS/ICMSSN101/orig` | `imposto_ICMS_ICMSSN101_orig` | Origem da mercadoria para fins do ICMS. | Código; consultar a tabela de origem abaixo. |
| `NFe/infNFe/det/imposto/ICMS/ICMSSN101/pCredSN` | `imposto_ICMS_ICMSSN101_pCredSN` | Percentual de crédito do ICMS no Simples Nacional. | Percentual; não é margem comercial. |
| `NFe/infNFe/det/imposto/ICMS/ICMSSN101/vCredICMSSN` | `imposto_ICMS_ICMSSN101_vCredICMSSN` | Valor de crédito do ICMS no Simples Nacional. | R$; sua presença não decide, por si só, o aproveitamento pela empresa. |
| `NFe/infNFe/det/imposto/ICMS/ICMSSN102/CSOSN` | `imposto_ICMS_ICMSSN102_CSOSN` | Código da situação da operação no Simples Nacional para ICMS. | Código textual; consultar os códigos encontrados abaixo. Não é o CRT da empresa. |
| `NFe/infNFe/det/imposto/ICMS/ICMSSN102/orig` | `imposto_ICMS_ICMSSN102_orig` | Origem da mercadoria para fins do ICMS. | Código; consultar a tabela de origem abaixo. |
| `NFe/infNFe/det/imposto/ICMS/ICMSSN900/CSOSN` | `imposto_ICMS_ICMSSN900_CSOSN` | Código da situação da operação no Simples Nacional para ICMS. | Código textual; consultar os códigos encontrados abaixo. Não é o CRT da empresa. |
| `NFe/infNFe/det/imposto/ICMS/ICMSSN900/modBC` | `imposto_ICMS_ICMSSN900_modBC` | Modalidade de determinação da base de cálculo do ICMS. | Código; consultar a tabela modBC abaixo. |
| `NFe/infNFe/det/imposto/ICMS/ICMSSN900/modBCST` | `imposto_ICMS_ICMSSN900_modBCST` | Modalidade de determinação da base de cálculo do ICMS por substituição tributária. | Código; consultar a tabela modBCST abaixo. |
| `NFe/infNFe/det/imposto/ICMS/ICMSSN900/orig` | `imposto_ICMS_ICMSSN900_orig` | Origem da mercadoria para fins do ICMS. | Código; consultar a tabela de origem abaixo. |
| `NFe/infNFe/det/imposto/ICMS/ICMSSN900/pCredSN` | `imposto_ICMS_ICMSSN900_pCredSN` | Percentual de crédito do ICMS no Simples Nacional. | Percentual; não é margem comercial. |
| `NFe/infNFe/det/imposto/ICMS/ICMSSN900/pICMS` | `imposto_ICMS_ICMSSN900_pICMS` | Alíquota do ICMS. | Percentual: 18,00 significa 18%. |
| `NFe/infNFe/det/imposto/ICMS/ICMSSN900/pICMSST` | `imposto_ICMS_ICMSSN900_pICMSST` | Alíquota do ICMS por substituição tributária. | Percentual; não é um valor em reais. |
| `NFe/infNFe/det/imposto/ICMS/ICMSSN900/pMVAST` | `imposto_ICMS_ICMSSN900_pMVAST` | Margem de valor agregado usada no cálculo do ICMS-ST. | Percentual fiscal; não é a margem de lucro comercial do produto. |
| `NFe/infNFe/det/imposto/ICMS/ICMSSN900/vBC` | `imposto_ICMS_ICMSSN900_vBC` | Base de cálculo do tributo neste grupo. | R$. A base pode diferir do valor bruto do produto. |
| `NFe/infNFe/det/imposto/ICMS/ICMSSN900/vBCST` | `imposto_ICMS_ICMSSN900_vBCST` | Base de cálculo do ICMS-ST. | R$; diferente da base do ICMS próprio. |
| `NFe/infNFe/det/imposto/ICMS/ICMSSN900/vCredICMSSN` | `imposto_ICMS_ICMSSN900_vCredICMSSN` | Valor de crédito do ICMS no Simples Nacional. | R$; sua presença não decide, por si só, o aproveitamento pela empresa. |
| `NFe/infNFe/det/imposto/ICMS/ICMSSN900/vICMS` | `imposto_ICMS_ICMSSN900_vICMS` | Valor do ICMS informado para o item neste grupo. | R$. O extrator copia o valor, sem recalcular. |
| `NFe/infNFe/det/imposto/ICMS/ICMSSN900/vICMSST` | `imposto_ICMS_ICMSSN900_vICMSST` | Valor do ICMS por substituição tributária. | R$; não somar indiscriminadamente com ICMS próprio para calcular custo. |
| `NFe/infNFe/det/imposto/IPI/IPINT/CST` | `imposto_IPI_IPINT_CST` | Código da situação tributária de IPI. | Código textual; preservar zeros e interpretar dentro deste tributo e grupo. Consulte os códigos encontrados abaixo. |
| `NFe/infNFe/det/imposto/IPI/IPITrib/CST` | `imposto_IPI_IPITrib_CST` | Código da situação tributária de IPI. | Código textual; preservar zeros e interpretar dentro deste tributo e grupo. Consulte os códigos encontrados abaixo. |
| `NFe/infNFe/det/imposto/IPI/IPITrib/pIPI` | `imposto_IPI_IPITrib_pIPI` | Alíquota do IPI. | Percentual. |
| `NFe/infNFe/det/imposto/IPI/IPITrib/qUnid` | `imposto_IPI_IPITrib_qUnid` | Quantidade para cálculo do IPI por unidade. | Quantidade; usada quando a tributação é por unidade. |
| `NFe/infNFe/det/imposto/IPI/IPITrib/vBC` | `imposto_IPI_IPITrib_vBC` | Base de cálculo do tributo neste grupo. | R$. A base pode diferir do valor bruto do produto. |
| `NFe/infNFe/det/imposto/IPI/IPITrib/vIPI` | `imposto_IPI_IPITrib_vIPI` | Valor do IPI do item. | R$; não é o total de tributos. |
| `NFe/infNFe/det/imposto/IPI/IPITrib/vUnid` | `imposto_IPI_IPITrib_vUnid` | Valor do IPI por unidade para cálculo específico. | R$/unidade; não é o preço comercial do produto. |
| `NFe/infNFe/det/imposto/IPI/cEnq` | `imposto_IPI_cEnq` | Código de enquadramento legal do IPI. | Código textual; consultar tabela oficial de enquadramento, preservando zeros. |
| `NFe/infNFe/det/imposto/IPI/qSelo` | `imposto_IPI_qSelo` | Quantidade de selos de controle do IPI. | Quantidade de selos; não é quantidade comercial do produto. |
| `NFe/infNFe/det/imposto/PIS/PISAliq/CST` | `imposto_PIS_PISAliq_CST` | Código da situação tributária de PIS. | Código textual; preservar zeros e interpretar dentro deste tributo e grupo. Consulte os códigos encontrados abaixo. |
| `NFe/infNFe/det/imposto/PIS/PISAliq/pPIS` | `imposto_PIS_PISAliq_pPIS` | Alíquota de PIS. | Percentual, não R$. |
| `NFe/infNFe/det/imposto/PIS/PISAliq/vBC` | `imposto_PIS_PISAliq_vBC` | Base de cálculo do tributo neste grupo. | R$. A base pode diferir do valor bruto do produto. |
| `NFe/infNFe/det/imposto/PIS/PISAliq/vPIS` | `imposto_PIS_PISAliq_vPIS` | Valor de PIS neste grupo do item. | R$; copiado sem recalcular. |
| `NFe/infNFe/det/imposto/PIS/PISNT/CST` | `imposto_PIS_PISNT_CST` | Código da situação tributária de PIS. | Código textual; preservar zeros e interpretar dentro deste tributo e grupo. Consulte os códigos encontrados abaixo. |
| `NFe/infNFe/det/imposto/PIS/PISOutr/CST` | `imposto_PIS_PISOutr_CST` | Código da situação tributária de PIS. | Código textual; preservar zeros e interpretar dentro deste tributo e grupo. Consulte os códigos encontrados abaixo. |
| `NFe/infNFe/det/imposto/PIS/PISOutr/pPIS` | `imposto_PIS_PISOutr_pPIS` | Alíquota de PIS. | Percentual, não R$. |
| `NFe/infNFe/det/imposto/PIS/PISOutr/qBCProd` | `imposto_PIS_PISOutr_qBCProd` | Quantidade usada como base para PIS. | Quantidade para cálculo por unidade; não é uma base em reais. |
| `NFe/infNFe/det/imposto/PIS/PISOutr/vAliqProd` | `imposto_PIS_PISOutr_vAliqProd` | Alíquota em valor por unidade de PIS. | R$/unidade; não percentual e não preço de venda do produto. |
| `NFe/infNFe/det/imposto/PIS/PISOutr/vBC` | `imposto_PIS_PISOutr_vBC` | Base de cálculo do tributo neste grupo. | R$. A base pode diferir do valor bruto do produto. |
| `NFe/infNFe/det/imposto/PIS/PISOutr/vPIS` | `imposto_PIS_PISOutr_vPIS` | Valor de PIS neste grupo do item. | R$; copiado sem recalcular. |
| `NFe/infNFe/det/imposto/vTotTrib` | `imposto_vTotTrib` | Valor aproximado dos tributos incidentes sobre o item. | R$. Informação aproximada de transparência tributária; não é soma calculada pelo extrator nem custo tributário líquido. |

## 5. Totais da nota

As 18 colunas abaixo correspondem a campos selecionados de `NFe/infNFe/total/ICMSTot`. Apesar do nome do grupo, ele também contém totais de produtos, descontos e outros tributos. Os caminhos foram conferidos na árvore do leiaute publicada pela SEF/MG, indicada nas referências. O CSV confirma os nomes das colunas; a correspondência descrita segue as tags desse grupo. A verificação direta do mapeamento implementado depende do script Python.

**Todos esses valores são monetários, em reais, e pertencem à nota inteira.** Eles são repetidos nas linhas dos itens, sem rateio e sem recálculo. Vazio significa ausência do campo; `0` ou `0,00` significa zero informado. Essas colunas não são alíquotas.

Por exemplo: se uma nota de R$ 500,00 tem cinco itens, `total_nota_valor_final` aparece como `500,00` nas cinco linhas. Somá-las produziria R$ 2.500,00, contando a mesma nota cinco vezes. Para totalizar várias notas, considerar uma única ocorrência por `chave_nfe`, após conferir duplicidades e consistência dos valores. Não eliminar notas diferentes só porque têm o mesmo valor total.

| Caminho no XML / origem | Coluna na tabela | Significado | Como interpretar |
|---|---|---|---|
| `NFe/infNFe/total/ICMSTot/vProd` | `total_nota_valor_produtos` | Valor total dos produtos e serviços informado em ICMSTot. | R$. Não é o valor final da nota. Comparar com os valores dos itens que participam da totalização, observando `compoe_total_nota`. |
| `NFe/infNFe/total/ICMSTot/vNF` | `total_nota_valor_final` | Valor total da NF-e informado em ICMSTot. | R$. Inclui os componentes previstos na totalização do XML. Não equivale a lucro, valor recebido ou valor de um item. A exclusão das colunas de frete e seguro não os subtrai deste valor. |
| `NFe/infNFe/total/ICMSTot/vDesc` | `total_nota_valor_desconto` | Valor total dos descontos da nota. | R$. Valor monetário, não percentual. Não representa o desconto de cada item separadamente. |
| `NFe/infNFe/total/ICMSTot/vOutro` | `total_nota_valor_outros` | Valor total de outras despesas acessórias da nota. | R$. Não representa automaticamente todas as despesas da empresa nem o custo completo da operação. |
| `NFe/infNFe/total/ICMSTot/vBC` | `total_nota_base_icms` | Base de cálculo total do ICMS. | R$. É uma base monetária, não alíquota nem imposto a pagar. Pode diferir do total dos produtos. |
| `NFe/infNFe/total/ICMSTot/vICMS` | `total_nota_valor_icms` | Valor total do ICMS informado na nota. | R$. Não confundir com a base `total_nota_base_icms` ou com ICMS-ST. Não determina sozinho crédito ou débito fiscal da empresa analisada. |
| `NFe/infNFe/total/ICMSTot/vICMSDeson` | `total_nota_valor_icms_desonerado` | Valor total do ICMS desonerado. | R$. Distinguir do ICMS destacado; não tratar automaticamente como imposto pago ou desconto comercial. |
| `NFe/infNFe/total/ICMSTot/vFCP` | `total_nota_valor_fcp` | Valor total do Fundo de Combate à Pobreza (FCP). | R$. Distinguir dos totais de FCP por substituição tributária e de FCP retido anteriormente. |
| `NFe/infNFe/total/ICMSTot/vBCST` | `total_nota_base_icms_st` | Base de cálculo total do ICMS por substituição tributária. | R$. É base monetária do ICMS-ST, não o valor do imposto nem a base do ICMS próprio. |
| `NFe/infNFe/total/ICMSTot/vST` | `total_nota_valor_icms_st` | Valor total do ICMS por substituição tributária. | R$. A tag do total é `vST`; nos grupos dos itens, o valor pode aparecer como `vICMSST`. Não confundir com ICMS retido anteriormente. |
| `NFe/infNFe/total/ICMSTot/vFCPST` | `total_nota_valor_fcp_st` | Valor total do FCP por substituição tributária. | R$. Distinguir de `total_nota_valor_fcp` e do FCP retido anteriormente. |
| `NFe/infNFe/total/ICMSTot/vFCPSTRet` | `total_nota_valor_fcp_st_retido` | Valor total do FCP retido anteriormente por substituição tributária. | R$. Refere-se à retenção anterior; não representa necessariamente uma nova cobrança nesta nota. |
| `NFe/infNFe/total/ICMSTot/vII` | `total_nota_valor_imposto_importacao` | Valor total do Imposto de Importação. | R$. Não representa o custo completo de importação nem todas as despesas aduaneiras. |
| `NFe/infNFe/total/ICMSTot/vIPI` | `total_nota_valor_ipi` | Valor total do IPI informado na nota. | R$. Distinguir do IPI devolvido. A presença do valor não decide seu aproveitamento como crédito. |
| `NFe/infNFe/total/ICMSTot/vIPIDevol` | `total_nota_valor_ipi_devolvido` | Valor total do IPI devolvido. | R$. Relacionado à devolução; não confundir com o total de IPI destacado em `vIPI`. |
| `NFe/infNFe/total/ICMSTot/vPIS` | `total_nota_valor_pis` | Valor total do PIS informado em ICMSTot. | R$. Não é alíquota nem base de cálculo. Não determina sozinho a contribuição efetivamente devida pela empresa. |
| `NFe/infNFe/total/ICMSTot/vCOFINS` | `total_nota_valor_cofins` | Valor total da COFINS informado em ICMSTot. | R$. Não é alíquota nem base de cálculo. Não determina sozinho a contribuição efetivamente devida pela empresa. |
| `NFe/infNFe/total/ICMSTot/vTotTrib` | `total_nota_valor_aproximado_tributos` | Valor total aproximado dos tributos informado na nota. | R$. Informação aproximada de transparência tributária. Não é soma calculada pelo extrator, custo tributário líquido nem valor que deva ser acrescentado ao total da nota. |

Os tributos de cada item continuam nas colunas `imposto_` e `impostoDevol_`. Não somar um total da nota com os valores dos itens correspondentes: isso pode contar a mesma informação duas vezes. A presença dos totais não constitui rateio de tributos ou despesas por produto.

## 6. Códigos: leitura dos campos fiscais

As tabelas abaixo ajudam a ler os códigos. Os códigos encontrados descrevem o conteúdo da amostra; não certificam que seu uso fiscal está correto. Quando surgirem outros códigos, consultar a referência oficial correspondente.

### Origem da mercadoria (`orig`)

| Código | Interpretação |
|---|---|
| 0 | Nacional, fora das situações específicas dos códigos 3, 4, 5 e 8. |
| 1 | Estrangeira, importação direta, fora do código 6. |
| 2 | Estrangeira, adquirida no mercado interno, fora do código 7. |
| 3 | Nacional, conteúdo de importação superior a 40% e até 70%. |
| 4 | Nacional, produção conforme processos produtivos básicos previstos na legislação. |
| 5 | Nacional, conteúdo de importação de até 40%. |
| 6 | Estrangeira, importação direta, sem similar nacional segundo a lista aplicável, e gás natural. |
| 7 | Estrangeira, adquirida no mercado interno, sem similar nacional segundo a lista aplicável, e gás natural. |
| 8 | Nacional, conteúdo de importação superior a 70%. |

### Modalidade da base de cálculo (`modBC` e `modBCST`)

| Código | `modBC` — ICMS próprio | `modBCST` — substituição tributária |
|---|---|---|
| 0 | Margem de valor agregado. | Preço tabelado ou máximo sugerido. |
| 1 | Pauta. | Lista negativa. |
| 2 | Preço tabelado máximo. | Lista positiva. |
| 3 | Valor da operação. | Lista neutra. |
| 4 | Não se aplica nesta enumeração. | Margem de valor agregado. |
| 5 | Não se aplica nesta enumeração. | Pauta. |
| 6 | Não se aplica nesta enumeração. | Valor da operação. |

### Situações tributárias encontradas na amostra

**O mesmo número não tem significado universal.** Por exemplo, CST `00` do ICMS e CST `000` do IBS/CBS pertencem a tabelas diferentes.

| Tributo / campo | Código encontrado | Interpretação resumida |
|---|---|---|
| ICMS / CST | 00 | Tributação integral. |
| ICMS / CST | 10 | Tributação com cobrança de ICMS por substituição tributária. |
| ICMS / CST | 60 | ICMS cobrado anteriormente por substituição tributária. |
| ICMS / CSOSN | 101 | Tributação no Simples Nacional com permissão de crédito. |
| ICMS / CSOSN | 102 | Tributação no Simples Nacional sem permissão de crédito. |
| ICMS / CSOSN | 900 | Outras situações. |
| PIS ou COFINS / CST | 01 | Operação tributável pela alíquota básica. |
| PIS ou COFINS / CST | 02 | Operação tributável por alíquota diferenciada. |
| PIS ou COFINS / CST | 04 | Tributação monofásica: revenda com alíquota zero. |
| PIS ou COFINS / CST | 06 | Operação tributável com alíquota zero. |
| PIS ou COFINS / CST | 07 | Operação isenta da contribuição. |
| PIS ou COFINS / CST | 08 | Operação sem incidência da contribuição. |
| PIS ou COFINS / CST | 49 | Outras operações de saída. |
| PIS ou COFINS / CST | 99 | Outras operações. |
| IPI / CST | 50 | Saída tributada. |
| IPI / CST | 51 | Saída com alíquota zero. |
| IPI / CST | 52 | Saída isenta. |
| IPI / CST | 53 | Saída não tributada. |
| IPI / CST | 99 | Outras saídas. |
| IBS/CBS / CST | 000 | Tributação integral. |
| IBS/CBS / CST | 200 | Alíquota reduzida. |
| IBS/CBS / CST | 410 | Imunidade e não incidência. |

`cClassTrib` detalha a classificação do IBS/CBS em conjunto com o CST. Sua tabela pode ser atualizada; este documento não fixa todas as classificações nem regras de cálculo.

## 7. Limites e manutenção do dicionário

- A extração inclui 18 totais selecionados de `ICMSTot`. Não inclui os grupos de cobrança, pagamento e transporte, nem colunas de frete e seguro. Também não inclui os totais específicos de IBS/CBS, IS ou ISSQN. O valor final `vNF` é preservado conforme o XML, sem descontar componentes omitidos das colunas. Esta tabela prepara os dados; não calcula lucro real.
- O CSV conferido contém 51 colunas de identificação, partes e produto, 18 colunas de totais da nota e 95 colunas de tributos dos itens: 164 ao todo. Novos arquivos podem acrescentar outras colunas fiscais. A ordem deve ser consultada no cabeçalho do CSV.
- Se houver grupos fiscais repetidos, o extrator adiciona índices ao caminho para evitar sobrescrever valores. Esses casos devem ser documentados quando aparecerem.
- `destinatario_nome_fantasia` e `destinatario_crt` são colunas reservadas pelo código atual, sem correspondência padrão no grupo `dest`. A documentação registra a limitação; não modifica o código nem preenche valores por suposição.
- A categoria comercial ainda não é produzida por este extrator. Conforme a decisão do projeto, sua classificação pelo NCM real precisa acontecer antes da pseudonimização do NCM no ambiente acadêmico.
- Conferir a versão do leiaute e as tabelas oficiais ao atualizar classificações fiscais. Este dicionário explica os campos; não valida a tributação aplicada.

## Referências para conferência

- [Portal Nacional da NF-e — manuais](https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=33ol5hhSYZk=): Manual de Orientação do Contribuinte e Anexo I (leiaute e regras de validação).
- [SEF/MG — árvore do leiaute NF-e, PL_010b_NT2025_002_v1.30](https://portalsped.fazenda.mg.gov.br/spedmg/nfe/download/EstruturaNFe.html): localização dos campos e grupos.
- [SVRS — Portal da Conformidade Fácil](https://dfe-portal.svrs.rs.gov.br/CFF/ClassificacaoTributaria): tabelas e recursos da Reforma Tributária do Consumo, incluindo CST e classificação IBS/CBS.
- [Esquema NF-e v4.00, cópia mantida no NFePHP](https://github.com/nfephp-org/sped-nfe/blob/master/schemes/PL_010_V1.30/leiauteNFe_v4.00.xsd) e [tipos básicos RTC](https://github.com/nfephp-org/sped-nfe/blob/master/schemes/PL_010_V1.30/DFeTiposBasicos_v1.00.xsd): anotações de campos do pacote de esquemas; cópias de consulta, com procedência indicada, não substituem a publicação oficial.
- `etl/extrair_tabela_verificada.py`: referência dos nomes efetivamente criados e das transformações realizadas pelo FiscalMind.
