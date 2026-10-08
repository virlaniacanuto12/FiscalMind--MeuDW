# Dicionário de colunas — FiscalMind

Este documento descreve as colunas produzidas pelo extrator `etl/extrair_tabela.py`.

A tabela possui uma estrutura fixa para identificação da NF-e, partes, produto e totais, além de colunas tributárias criadas dinamicamente conforme os grupos encontrados nos XMLs processados.

Por esse motivo, o número total de colunas pode variar entre execuções que utilizem conjuntos diferentes de NF-e.

---

## Como ler a tabela

- **Uma linha corresponde a um item (`det`) de uma NF-e.** Informações pertencentes à nota e às partes se repetem nas linhas de seus itens.

- **As colunas `total_nota_` pertencem à NF-e inteira.** Não devem ser somadas diretamente linha a linha. Para análises por nota, considerar uma única ocorrência por `chave_nfe`.

- **Caminho no XML** indica a origem do campo. `/` representa a entrada em um grupo e `@` representa um atributo.

- **Coluna na tabela** representa o nome produzido pelo extrator.

- As colunas tributárias preservam o caminho do XML substituindo `/` por `_`.

- **Vazio não é igual a zero.** Campo vazio significa ausência da tag. Um valor como `0.00` significa que o zero foi explicitamente informado no XML.

- O CSV usa `;` como separador de colunas e, por padrão, ponto como separador decimal.

- Chaves, documentos, GTINs, NCMs, CESTs, CFOPs e demais códigos devem ser tratados como texto.

- Os valores são copiados do XML. O extrator não recalcula tributos, totais, margens ou custos.

- Emitente e destinatário não são automaticamente fornecedor e cliente do FiscalMind. Essa classificação ocorre posteriormente.

---

# 1. Identificação da nota e protocolo

| Caminho no XML / origem | Coluna | Significado | Como interpretar |
|---|---|---|---|
| Caminho relativo do arquivo | `arquivo_origem` | XML que originou a linha. | Utilizado para rastreabilidade da extração. Não determina a chave da NF-e. |
| `NFe/infNFe/@Id` | `chave_nfe` | Chave de acesso da NF-e. | O prefixo `NFe` é removido. Armazenada como texto de 44 caracteres alfanuméricos. |
| `NFe/infNFe/@versao` | `versao_nfe` | Versão do leiaute da NF-e. | Preserva o valor informado no atributo `versao`. |
| `NFe/infNFe/ide/nNF` | `numero_nota` | Número da NF-e. | Identificador da nota; não é chave global isoladamente. |
| `NFe/infNFe/ide/serie` | `serie` | Série da NF-e. | Código textual. |
| `NFe/infNFe/ide/mod` | `modelo` | Modelo do documento fiscal. | Para NF-e, normalmente `55`. |
| `NFe/infNFe/ide/dhEmi` ou `dEmi` | `data_hora_emissao` | Data ou data/hora de emissão. | Preserva o conteúdo informado no XML. |
| Derivada de `dhEmi` ou `dEmi` | `data_emissao` | Data de emissão. | Primeiros dez caracteres da emissão, no formato `AAAA-MM-DD`. |
| `NFe/infNFe/ide/natOp` | `natureza_operacao` | Natureza da operação. | Descrição textual informada no documento. Não substitui o CFOP. |
| `NFe/infNFe/ide/tpNF` | `tipo_nfe` | Tipo de operação informado na NF-e. | Deve ser interpretado no contexto do documento e da empresa analisada. |
| `NFe/infNFe/ide/finNFe` | `finalidade_nfe` | Finalidade da NF-e. | Permite distinguir operações normais, complementares, devoluções e outras finalidades. |
| `NFe/infNFe/ide/idDest` | `destino_operacao` | Destino da operação. | Indica operação interna, interestadual ou exterior, conforme código informado. |
| `NFe/infNFe/ide/tpAmb` | `ambiente` | Ambiente de emissão. | Produção ou homologação. |
| `nfeProc/protNFe/infProt/cStat` | `status_protocolo` | Código de status registrado no protocolo. | Pode ficar vazio quando o XML não contém protocolo. Não representa sozinho eventos posteriores. |

---

# 2. Emitente

| Caminho no XML | Coluna | Significado | Como interpretar |
|---|---|---|---|
| Derivada da identificação preenchida | `emitente_tipo_documento` | Tipo do documento. | `CNPJ` ou `CPF`, conforme o campo presente. |
| `emit/CNPJ` ou `emit/CPF` | `emitente_documento` | Documento do emitente. | Tratar como texto. |
| `emit/xNome` | `emitente_nome` | Nome ou razão social. | Texto informado no XML. |
| `emit/xFant` | `emitente_nome_fantasia` | Nome fantasia. | Campo opcional. |
| `emit/IE` | `emitente_ie` | Inscrição estadual. | Identificador textual. |
| `emit/CRT` | `emitente_crt` | Código do regime tributário. | Deve ser interpretado conforme tabela correspondente. |
| `emit/enderEmit/cMun` | `emitente_codigo_municipio` | Código do município. | Código cadastral; tratar como texto. |
| `emit/enderEmit/xMun` | `emitente_municipio` | Município. | Texto do endereço. |
| `emit/enderEmit/UF` | `emitente_uf` | Unidade federativa. | Sigla da UF. |
| `emit/enderEmit/xBairro` | `emitente_bairro` | Bairro. | Texto do endereço. |

---

# 3. Destinatário

| Caminho no XML | Coluna | Significado | Como interpretar |
|---|---|---|---|
| Derivada da identificação preenchida | `destinatario_tipo_documento` | Tipo do documento. | Pode ser `CNPJ`, `CPF` ou `idEstrangeiro`. |
| `dest/CNPJ`, `dest/CPF` ou `dest/idEstrangeiro` | `destinatario_documento` | Documento ou identificação do destinatário. | Tratar como texto. |
| `dest/xNome` | `destinatario_nome` | Nome ou razão social. | Texto informado no XML. |
| `dest/IE` | `destinatario_ie` | Inscrição estadual. | Pode estar ausente. |
| `dest/enderDest/cMun` | `destinatario_codigo_municipio` | Código do município. | Código cadastral; tratar como texto. |
| `dest/enderDest/xMun` | `destinatario_municipio` | Município. | Texto do endereço. |
| `dest/enderDest/UF` | `destinatario_uf` | Unidade federativa. | Sigla da UF. |
| `dest/enderDest/xBairro` | `destinatario_bairro` | Bairro. | Texto do endereço. |

---

# 4. Item e produto

| Caminho no XML | Coluna | Significado | Como interpretar |
|---|---|---|---|
| `det/@nItem` | `numero_item` | Número sequencial do item na NF-e. | Identifica o item dentro da nota. |
| `det/prod/cProd` | `codigo_produto` | Código do produto utilizado pelo emitente. | Não deve ser considerado identificador universal entre empresas. |
| `det/prod/xProd` | `descricao_produto` | Descrição do produto ou serviço. | Texto informado no XML. |
| `det/prod/NCM` | `ncm` | Nomenclatura Comum do Mercosul. | Código fiscal; tratar como texto. |
| `det/prod/CEST` | `cest` | Código Especificador da Substituição Tributária. | Campo opcional; tratar como texto. |
| `det/prod/CFOP` | `cfop` | Código Fiscal de Operações e Prestações. | Descreve a natureza fiscal da operação do item. Deve ser interpretado conforme tabela oficial vigente. |
| `det/prod/cEAN` | `gtin_comercial` | GTIN da unidade comercial. | Pode conter indicação de ausência de GTIN. |
| `det/prod/uCom` | `unidade_comercial` | Unidade comercial. | Ex.: `UN`, `CX`, `KG`. |
| `det/prod/qCom` | `quantidade_comercial` | Quantidade comercial. | Medida expressa na unidade comercial. |
| `det/prod/vUnCom` | `valor_unitario_comercial` | Valor unitário comercial. | Valor por unidade comercial. |
| `det/prod/vProd` | `valor_produto` | Valor bruto do item. | Não corresponde necessariamente ao valor final da operação. |
| `det/prod/cEANTrib` | `gtin_tributavel` | GTIN da unidade tributável. | Pode diferir do GTIN comercial. |
| `det/prod/uTrib` | `unidade_tributavel` | Unidade utilizada para tributação. | Pode diferir da unidade comercial. |
| `det/prod/qTrib` | `quantidade_tributavel` | Quantidade tributável. | Expressa na unidade tributável. |
| `det/prod/vUnTrib` | `valor_unitario_tributavel` | Valor unitário tributável. | Pode diferir do valor unitário comercial. |
| `det/prod/vDesc` | `valor_desconto` | Desconto do item. | Valor monetário, não percentual. |
| `det/prod/vOutro` | `valor_outros` | Outras despesas acessórias do item. | Valor informado no XML. |
| `det/prod/indTot` | `compoe_total_nota` | Indica participação do item no total. | Código, não valor monetário. |

---

# 5. Tributos do item

Os campos tributários não possuem um conjunto fixo de colunas.

O extrator percorre os grupos:

```text
imposto
impostoDevol
```

e cria colunas utilizando o caminho completo da estrutura XML.

Exemplo:

```text
NFe/infNFe/det/imposto/ICMS/ICMS00/vBC
```

torna-se:

```text
imposto_ICMS_ICMS00_vBC
```

O mesmo mecanismo é utilizado para ICMS, IPI, PIS, COFINS, IBS/CBS e demais grupos encontrados no XML.

Novos grupos presentes em outros documentos podem gerar novas colunas sem necessidade de alteração manual da lista de campos tributários.

## Exemplos

| Caminho no XML | Coluna | Significado |
|---|---|---|
| `imposto/ICMS/ICMS00/orig` | `imposto_ICMS_ICMS00_orig` | Origem da mercadoria. |
| `imposto/ICMS/ICMS00/CST` | `imposto_ICMS_ICMS00_CST` | Situação tributária do ICMS. |
| `imposto/ICMS/ICMS00/vBC` | `imposto_ICMS_ICMS00_vBC` | Base de cálculo do ICMS. |
| `imposto/ICMS/ICMS00/pICMS` | `imposto_ICMS_ICMS00_pICMS` | Alíquota do ICMS. |
| `imposto/ICMS/ICMS00/vICMS` | `imposto_ICMS_ICMS00_vICMS` | Valor do ICMS. |
| `imposto/PIS/PISAliq/CST` | `imposto_PIS_PISAliq_CST` | Situação tributária do PIS. |
| `imposto/PIS/PISAliq/pPIS` | `imposto_PIS_PISAliq_pPIS` | Alíquota do PIS. |
| `imposto/PIS/PISAliq/vPIS` | `imposto_PIS_PISAliq_vPIS` | Valor do PIS. |
| `imposto/COFINS/COFINSAliq/CST` | `imposto_COFINS_COFINSAliq_CST` | Situação tributária da COFINS. |
| `imposto/COFINS/COFINSAliq/pCOFINS` | `imposto_COFINS_COFINSAliq_pCOFINS` | Alíquota da COFINS. |
| `imposto/COFINS/COFINSAliq/vCOFINS` | `imposto_COFINS_COFINSAliq_vCOFINS` | Valor da COFINS. |
| `imposto/IPI/IPITrib/vIPI` | `imposto_IPI_IPITrib_vIPI` | Valor do IPI. |
| `impostoDevol/IPI/vIPIDevol` | `impostoDevol_IPI_vIPIDevol` | Valor do IPI devolvido. |
| `imposto/vTotTrib` | `imposto_vTotTrib` | Valor aproximado dos tributos do item. |

Os valores são copiados do XML e não são recalculados pelo extrator.

---

# 6. Totais da NF-e

Os campos abaixo são extraídos de:

```text
NFe/infNFe/total/ICMSTot
```

Esses valores pertencem à NF-e inteira e são repetidos nas linhas de seus itens.

| Tag | Coluna | Significado |
|---|---|---|
| `vProd` | `total_nota_valor_produtos` | Valor total dos produtos. |
| `vNF` | `total_nota_valor_final` | Valor final informado da NF-e. |
| `vDesc` | `total_nota_valor_desconto` | Total de descontos. |
| `vOutro` | `total_nota_valor_outros` | Outras despesas acessórias. |
| `vBC` | `total_nota_base_icms` | Base total de cálculo do ICMS. |
| `vICMS` | `total_nota_valor_icms` | Valor total do ICMS. |
| `vICMSDeson` | `total_nota_valor_icms_desonerado` | Valor total do ICMS desonerado. |
| `vFCP` | `total_nota_valor_fcp` | Valor total do FCP. |
| `vBCST` | `total_nota_base_icms_st` | Base total do ICMS-ST. |
| `vST` | `total_nota_valor_icms_st` | Valor total do ICMS-ST. |
| `vFCPST` | `total_nota_valor_fcp_st` | Valor total do FCP-ST. |
| `vFCPSTRet` | `total_nota_valor_fcp_st_retido` | FCP-ST retido anteriormente. |
| `vII` | `total_nota_valor_imposto_importacao` | Valor total do Imposto de Importação. |
| `vIPI` | `total_nota_valor_ipi` | Valor total do IPI. |
| `vIPIDevol` | `total_nota_valor_ipi_devolvido` | Valor total do IPI devolvido. |
| `vPIS` | `total_nota_valor_pis` | Valor total do PIS. |
| `vCOFINS` | `total_nota_valor_cofins` | Valor total da COFINS. |
| `vTotTrib` | `total_nota_valor_aproximado_tributos` | Valor aproximado total dos tributos. |

Não somar essas colunas diretamente entre as linhas dos itens.

Para totalizações por NF-e, utilizar uma única ocorrência por `chave_nfe`.

---

# 7. Códigos fiscais

Os campos de código devem ser interpretados de acordo com sua própria tabela fiscal.

O mesmo valor numérico pode representar significados diferentes em tributos diferentes.

Por exemplo:

```text
CST do ICMS
CST do PIS
CST da COFINS
CST do IBS/CBS
```

não utilizam necessariamente a mesma tabela de significados.

O extrator preserva os códigos exatamente como informados no XML e não tenta convertê-los em descrições.

---

## Origem da mercadoria (`orig`)

| Código | Interpretação resumida |
|---|---|
| `0` | Nacional. |
| `1` | Estrangeira — importação direta. |
| `2` | Estrangeira — adquirida no mercado interno. |
| `3` | Nacional com conteúdo de importação conforme enquadramento correspondente. |
| `4` | Nacional produzida conforme processos produtivos previstos na legislação. |
| `5` | Nacional com conteúdo de importação conforme enquadramento correspondente. |
| `6` | Estrangeira — importação direta em condição específica. |
| `7` | Estrangeira — adquirida no mercado interno em condição específica. |
| `8` | Nacional com conteúdo de importação conforme enquadramento correspondente. |

A interpretação detalhada deve seguir a tabela fiscal oficial vigente.

---

# 8. CFOP e classificação da operação

A coluna:

```text
cfop
```

preserva o CFOP informado para cada item da NF-e.

O CFOP descreve a natureza fiscal da operação, mas o extrator não transforma automaticamente esse código em:

```text
compra
venda
fornecedor
cliente
```

Essa classificação pertence à etapa posterior de tratamento do Data Warehouse.

No FiscalMind, a classificação deverá considerar conjuntamente:

- CFOP;
- posição da empresa analisada na NF-e;
- emitente;
- destinatário;
- tipo da operação;
- finalidade da NF-e;
- demais regras necessárias.

---

# 9. Relatório da extração

Além da tabela intermediária, o extrator gera:

```text
tabela_nfe_relatorio.csv
```

com as colunas:

| Coluna | Significado |
|---|---|
| `arquivo_origem` | Arquivo XML processado. |
| `status` | Resultado da leitura do arquivo. |
| `quantidade_itens` | Quantidade de itens extraídos da NF-e. |
| `observacao` | Informação adicional ou motivo de erro. |

Um XML inválido não impede o processamento dos demais arquivos.

---

# 10. Duplicidades

Quando a mesma `chave_nfe` aparece mais de uma vez na mesma execução, a ocorrência é registrada no relatório.

O extrator não elimina automaticamente as linhas correspondentes.

A deduplicação pertence às etapas posteriores do pipeline.

---

# 11. Valores decimais

Por padrão, os valores são exportados com ponto decimal:

```text
18.00
5.90
125.5000
```

A opção:

```powershell
--decimal virgula
```

pode ser utilizada quando for necessária uma versão específica para visualização em planilhas configuradas com vírgula decimal.

---

# 12. Limitações

O extrator:

- não realiza validação completa por XSD;
- não valida assinatura digital;
- não consulta a SEFAZ;
- não verifica eventos posteriores ao XML processado;
- não recalcula tributos;
- não recalcula totais;
- não determina crédito tributário;
- não calcula margem ou lucro;
- não classifica automaticamente fornecedores e clientes;
- não determina automaticamente compra ou venda;
- não relaciona produtos equivalentes entre empresas;
- não carrega diretamente o Data Warehouse.

Seu objetivo é transformar os XMLs de NF-e em uma tabela intermediária estruturada.

---

# 13. Manutenção do dicionário

As colunas fixas são determinadas pelo código do extrator.

As colunas iniciadas por:

```text
imposto_
impostoDevol_
```

dependem dos grupos tributários efetivamente encontrados nos XMLs.

Portanto, novos conjuntos de documentos podem gerar novas colunas tributárias.

O cabeçalho do CSV produzido em cada execução representa a estrutura efetivamente encontrada naquele conjunto de documentos.

---

## Referências para conferência

- Portal Nacional da NF-e — documentação, notas técnicas, schemas e tabelas oficiais.
- Manual de Orientação do Contribuinte da NF-e.
- Schemas oficiais vigentes da NF-e.
- Tabelas fiscais oficiais utilizadas nos campos correspondentes.
- `etl/extrair_tabela.py` — implementação utilizada pelo FiscalMind.