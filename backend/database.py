from langchain_community.utilities import SQLDatabase

def build_uri(db_type, user, password, host, port, database):
    if db_type == "MySQL":
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
    elif db_type == "PostgreSQL":
        return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"
    return f"sqlite:///{database}"

def connect(db_type, user, password, host, port, database):
    uri = build_uri(db_type, user, password, host, port, database)
    return SQLDatabase.from_uri(uri, sample_rows_in_table_info=2)