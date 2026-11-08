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
