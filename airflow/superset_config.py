import os
from urllib.parse import quote_plus

# Chave de segurança da aplicação
SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]

# Senha do banco de metadados
senha = quote_plus(os.environ["SUPERSET_DB_PASSWORD"])

# Banco interno do Superset (PostgreSQL 16)
SQLALCHEMY_DATABASE_URI = (
    f"postgresql+psycopg2://superset:{senha}"
    "@superset-db:5432/superset"
)

# ------------------------------------------------------------
# Formato brasileiro de números e datas
# ------------------------------------------------------------
# Números: 1.234.567,89 e prefixo "R$ " nos formatos de moeda ($)
D3_FORMAT = {
    "decimal": ",",
    "thousands": ".",
    "grouping": [3],
    "currency": ["R$ ", ""],
}

# Datas: dd/mm/aaaa, nomes de meses e dias em português
D3_TIME_FORMAT = {
    "dateTime": "%A, %e de %B de %Y. %X",
    "date": "%d/%m/%Y",
    "time": "%H:%M:%S",
    "periods": ["AM", "PM"],
    "days": ["Domingo", "Segunda", "Terça", "Quarta",
             "Quinta", "Sexta", "Sábado"],
    "shortDays": ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"],
    "months": ["Janeiro", "Fevereiro", "Março", "Abril",
               "Maio", "Junho", "Julho", "Agosto",
               "Setembro", "Outubro", "Novembro", "Dezembro"],
    "shortMonths": ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
                    "Jul", "Ago", "Set", "Out", "Nov", "Dez"],
}

# Moedas disponíveis no campo "Metric currency" (BRL incluído)
CURRENCIES = ["BRL", "USD", "EUR"]

# Paleta personalizada do FiscalMind (ordem pensada para regiões e destaques)
EXTRA_CATEGORICAL_COLOR_SCHEMAS = [
    {
        "id": "fiscalmind_dark",
        "label": "FiscalMind Dark",
        "description": "Paleta escura FiscalMind",
        "colors": [
            "#2DD4BF",
            "#60A5FA",
            "#FBBF24",
            "#A78BFA",
            "#34D399",
            "#F472B6",
        ],
    }
]