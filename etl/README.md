# Extrator da tabela de NF-e — FiscalMind

## Objetivo

Gerar uma tabela intermediária com uma linha por item (`det`) de uma NF-e.

O programa lê todos os XMLs da pasta indicada e de suas subpastas.

---

## Requisitos e localização

- Python 3.10 ou superior.
- Nenhuma biblioteca adicional: o extrator utiliza apenas módulos da biblioteca padrão do Python.
- Script: `etl/extrair_tabela.py`.
- Pasta padrão de entrada dos XMLs: `data/inbox`.

No terminal do VS Code, aberto na raiz `FiscalMind--MeuDW`:

```powershell
python --version
python etl/extrair_tabela.py
```

Também é possível utilizar:

```powershell
py etl/extrair_tabela.py
```

### Saídas padrão

- `data/processados/tabela_nfe.csv`: tabela intermediária com uma linha por item da NF-e.
- `data/processados/tabela_nfe_relatorio.csv`: relatório da execução, com uma linha por arquivo processado.


É possível informar outros caminhos de entrada e saída:

```powershell
python etl/extrair_tabela.py --input data/inbox --output data/processados/teste.csv

---

## O que é extraído

### 1. Identificação da NF-e

- arquivo de origem;
- chave de acesso;
- versão da NF-e;
- número da nota;
- série;
- modelo;
- data e hora de emissão;
- data de emissão;
- natureza da operação;
- tipo da NF-e;
- finalidade;
- destino da operação;
- ambiente;
- código de status do protocolo, quando disponível.

### 2. Emitente

- tipo de documento;
- documento;
- nome;
- nome fantasia;
- inscrição estadual;
- regime tributário;
- código do município;
- município;
- UF;
- bairro.

### 3. Destinatário

- tipo de documento;
- documento;
- nome;
- inscrição estadual;
- código do município;
- município;
- UF;
- bairro.

### 4. Produto

- número do item;
- código do produto;
- descrição;
- NCM;
- CEST;
- CFOP;
- GTIN comercial;
- unidade comercial;
- quantidade comercial;
- valor unitário comercial;
- valor do produto;
- GTIN tributável;
- unidade tributável;
- quantidade tributável;
- valor unitário tributável;
- desconto;
- outras despesas do item;
- indicador de composição do total da NF-e.

### 5. Tributos dos itens

São extraídos todos os campos terminais encontrados nos grupos:

```text
imposto
impostoDevol
```

A hierarquia do XML é preservada no nome das colunas.

Por exemplo:

```text
imposto/ICMS/ICMS00/vBC
```

é transformado em:

```text
imposto_ICMS_ICMS00_vBC
```

Dessa forma, campos com o mesmo nome pertencentes a grupos tributários diferentes não são misturados.

O conjunto de colunas tributárias pode variar de acordo com os grupos existentes nos XMLs processados.

### 6. Totais selecionados da NF-e

São extraídos campos do grupo:

```text
NFe/infNFe/total/ICMSTot
```

incluindo:

- valor total dos produtos;
- valor final da nota;
- descontos;
- outras despesas;
- base de cálculo do ICMS;
- valor do ICMS;
- ICMS desonerado;
- FCP;
- base do ICMS-ST;
- ICMS-ST;
- FCP-ST;
- FCP-ST retido;
- Imposto de Importação;
- IPI;
- IPI devolvido;
- PIS;
- COFINS;
- valor aproximado dos tributos.

Não são extraídos os grupos de cobrança, pagamento e transporte, nem campos específicos de frete e seguro.

O valor final da NF-e (`vNF`) é preservado conforme informado no XML.

---

## Estrutura da tabela intermediária

Cada linha da tabela corresponde a um item (`det`) da NF-e.

Por isso, informações pertencentes à nota inteira, ao emitente, ao destinatário e aos totais são repetidas para cada item da mesma nota.

As colunas com prefixo:

```text
total_nota_
```

pertencem à nota inteira e não devem ser somadas diretamente linha a linha.

Por exemplo, se uma NF-e de R$ 500,00 possuir cinco itens, o valor total da nota será repetido nas cinco linhas. Somar diretamente essa coluna produziria R$ 2.500,00, contando a mesma NF-e cinco vezes.

Para análises por nota, deve-se considerar uma única ocorrência por `chave_nfe`.

---

## Identificação da NF-e

A chave de acesso é obtida diretamente do atributo:

```text
NFe/infNFe/@Id
```

O prefixo `NFe` é removido e o valor restante é armazenado em:

```text
chave_nfe
```

A chave é tratada como texto com 44 caracteres alfanuméricos.

O nome físico do arquivo XML não é utilizado para determinar a chave de acesso.

A versão do leiaute é obtida de:

```text
NFe/infNFe/@versao
```

e armazenada em:

```text
versao_nfe
```

---

## Como o programa funciona

O extrator é dividido em funções com responsabilidades específicas.

### `nome_tag`

Remove o namespace das tags XML.

### `filho`

Localiza um elemento filho pelo nome da tag.

### `texto`

Obtém o conteúdo textual de um elemento.

### `dados_parte`

Extrai os campos correspondentes ao emitente ou ao destinatário.

### `achatar_grupo`

Transforma a estrutura hierárquica dos grupos tributários em colunas da tabela.

### `extrair_arquivo`

Lê um XML de NF-e, verifica a estrutura mínima necessária e gera uma linha para cada item.

### `gerar_tabela`

Percorre os arquivos XML, executa a extração e produz:

- a tabela intermediária;
- o relatório de processamento.

### `main`

Interpreta os argumentos informados na linha de comando.

---

## Processamento dos arquivos

O extrator lê um XML por vez.

As linhas extraídas são armazenadas temporariamente enquanto o programa identifica todas as colunas tributárias presentes no conjunto de XMLs.

Depois disso, o CSV final é gravado e o arquivo temporário é removido automaticamente.

O extrator não mantém todos os XMLs ou itens simultaneamente em memória.

---

## Relatório de processamento

O arquivo:

```text
data/processados/tabela_nfe_relatorio.csv
```

possui as colunas:

- `arquivo_origem`;
- `status`;
- `quantidade_itens`;
- `observacao`.

O campo `status` pode assumir, entre outros, os valores:

```text
processado
erro
```

Quando um XML apresenta erro de leitura ou não contém a estrutura mínima esperada, ele não contribui com linhas para a tabela intermediária.

O erro é registrado no relatório e os demais XMLs continuam sendo processados.

A presença de um XML inválido pode, portanto, resultar em uma saída parcial sem interromper toda a extração.

Falhas gerais da execução, como pasta de entrada inexistente ou ausência de arquivos XML, continuam sendo tratadas como erro da execução.

---

## Tratamento de duplicidades

Se a mesma `chave_nfe` aparecer em mais de um arquivo durante a mesma execução, a ocorrência é registrada no relatório.

O extrator não remove automaticamente esses registros.


---

## Valores decimais

Por padrão, o extrator preserva o ponto como separador decimal:

```text
18.00
125.90
10.5000
```

Não há conversão para `float` durante a formatação do CSV, evitando alterações de precisão.

Quando necessário, pode ser gerada uma versão com vírgula decimal:

```powershell
python etl/extrair_tabela.py --decimal virgula
```

---

## Conferência em planilhas

O arquivo CSV utiliza:

```text
;
```

como separador de colunas.

Para importar no Excel:

1. utilize `Dados > De Texto/CSV`;
2. selecione a codificação UTF-8;
3. utilize `;` como delimitador;
4. mantenha documentos, chaves e códigos fiscais como texto.

No Google Planilhas, utilize `;` como separador durante a importação.

Caso a configuração regional da planilha não reconheça números com ponto decimal, pode ser gerada uma versão específica utilizando:

```powershell
python etl/extrair_tabela.py --decimal virgula
```

---

## Emitente, destinatário, fornecedor e cliente

Emitente e destinatário representam as partes registradas na NF-e.

Essas posições não são automaticamente equivalentes a fornecedor e cliente do FiscalMind.

A classificação deverá ocorrer posteriormente, durante o tratamento e a carga do Data Warehouse, considerando:

- a empresa analisada;
- sua posição na NF-e;
- o CFOP;
- o tipo da operação;
- a finalidade da NF-e;
- outras informações necessárias à classificação da operação.

O extrator apenas preserva os dados existentes no documento fiscal.

---

## Limitações

O extrator não:

- valida integralmente o XML contra os schemas XSD oficiais;
- valida assinatura digital;
- consulta a situação fiscal da NF-e em serviços da SEFAZ;
- verifica eventos posteriores, como cancelamento;
- recalcula dígito verificador;
- calcula tributos;
- recalcula totais da NF-e;
- determina crédito tributário;
- calcula margem ou custo;
- classifica automaticamente compra ou venda;
- classifica automaticamente fornecedor ou cliente;
- relaciona produtos equivalentes entre diferentes fornecedores;
- carrega diretamente o Data Warehouse.

Essas responsabilidades pertencem a etapas posteriores do pipeline.

---

A tabela produzida pelo extrator é uma camada intermediária e não corresponde ao modelo dimensional final do Data Warehouse.