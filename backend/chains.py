import re
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

def clean_query(raw: str) -> str:
    match = re.search(r"```sql\s*(.*?)\s*```", raw, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else raw.strip().rstrip(";")

def confidence_badge(result_text: str) -> tuple:
    if result_text.startswith("Query error"):
        return "red", "Low confidence — query failed"
    elif result_text == "(no rows returned)":
        return "orange", "Medium confidence — no rows returned"
    return "green", "High confidence — query executed successfully"

def build_sql_chain(db, llm, db_type):
    dialect = "PostgreSQL" if db_type == "PostgreSQL" else "SQLite" if db_type == "SQLite" else "MySQL"
    quote_char = '"' if db_type == "PostgreSQL" else "`"

    prompt = ChatPromptTemplate.from_template(f"""
You are an expert {dialect} query generator.
STRICT RULES:
- Output ONLY the raw SQL query
- No markdown, no backtick fences, no explanation
- Single line query only, no line breaks
- Use exact table and column names from the schema
- Use JOINs where needed based on foreign key relationships
- Never hallucinate columns that don't exist in the schema
- Use LIMIT 100 unless the question asks for aggregates or all records
- Wrap column names that have spaces with {quote_char}

DATABASE SCHEMA: {{schema}}
QUESTION: {{question}}
SQL QUERY:""")

    return (
        RunnablePassthrough.assign(schema=lambda _: db.get_table_info())
        | prompt
        | llm.bind(stop=["\nSQLResult:"])
        | StrOutputParser()
    )

def build_nl_chain(llm):
    prompt = ChatPromptTemplate.from_template("""
You are a helpful data analyst. Given the user question, SQL query, and result,
write a single sentence answer. No extra explanation.

User Question: {question}
SQL Query: {query}
Database Result: {result}

One sentence answer:""")

    return prompt | llm | StrOutputParser()

def build_chains(db, llm, db_type):
    return build_sql_chain(db, llm, db_type), build_nl_chain(llm)