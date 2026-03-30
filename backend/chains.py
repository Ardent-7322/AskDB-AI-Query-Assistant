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


def format_history(messages: list) -> str:
    # Sirf last 4 messages (2 exchanges)
    recent = messages[-4:] if len(messages) > 4 else messages
    history_lines = []
    for msg in recent:
        if msg["role"] == "user":
            history_lines.append(f"User: {msg['content']}")
        elif msg["role"] == "assistant" and msg.get("nl_answer"):
            history_lines.append(f"Assistant: {msg['nl_answer']}")
    return "\n".join(history_lines) if history_lines else "No previous conversation."

def build_sql_chain(db, llm, db_type):
    dialect = "PostgreSQL" if db_type == "PostgreSQL" else "SQLite" if db_type == "SQLite" else "MySQL"
    quote_char = '"' if db_type == "PostgreSQL" else "`"

    # ── Memory-aware SQL prompt ───────────────────────────────────────────────
    prompt = ChatPromptTemplate.from_template(f"""
You are an expert {dialect} query generator.

CONVERSATION HISTORY (use this to resolve follow-up questions like "what about last month?" or "show me those users"):
{{history}}

STRICT RULES:
- Output ONLY the raw SQL query
- No markdown, no backtick fences, no explanation
- Single line query only, no line breaks
- Use exact table and column names from the schema
- Use JOINs where needed based on foreign key relationships
- Never hallucinate columns that don't exist in the schema
- Use LIMIT 100 unless the question asks for aggregates or all records
- Wrap column names that have spaces with {quote_char}
- If the current question references something from history (e.g. "those products", "last result"), resolve it using the history above

DATABASE SCHEMA: {{schema}}
CURRENT QUESTION: {{question}}
SQL QUERY:""")

    return (
        RunnablePassthrough.assign(schema=lambda _: db.get_table_info())
        | prompt
        | llm.bind(stop=["\nSQLResult:"])
        | StrOutputParser()
    )


def build_retry_sql_chain(db, llm, db_type):
    """
    Used when first SQL attempt fails.
    Takes original question + failed query + error and returns a fixed query.
    """
    dialect = "PostgreSQL" if db_type == "PostgreSQL" else "SQLite" if db_type == "SQLite" else "MySQL"
    quote_char = '"' if db_type == "PostgreSQL" else "`"

    prompt = ChatPromptTemplate.from_template(f"""
You are an expert {dialect} query debugger.

The following SQL query failed with an error. Fix it and return ONLY the corrected SQL query.

STRICT RULES:
- Output ONLY the raw SQL query
- No markdown, no backtick fences, no explanation
- Single line query only
- Use exact table and column names from the schema
- Wrap column names that have spaces with {quote_char}

DATABASE SCHEMA: {{schema}}
ORIGINAL QUESTION: {{question}}
FAILED SQL QUERY: {{failed_query}}
ERROR MESSAGE: {{error}}
FIXED SQL QUERY:""")

    return (
        RunnablePassthrough.assign(schema=lambda _: db.get_table_info())
        | prompt
        | llm.bind(stop=["\nSQLResult:"])
        | StrOutputParser()
    )


def build_nl_chain(llm):
    # ── Memory-aware NL prompt ─────
    prompt = ChatPromptTemplate.from_template("""
You are a helpful data analyst. Given the conversation history, the current user question,
SQL query, and result, write a single clear sentence answer.
If the result references something from a previous question, mention that context briefly.
No extra explanation beyond one sentence.

CONVERSATION HISTORY:
{history}

Current User Question: {question}
SQL Query: {query}
Database Result: {result}

One sentence answer:""")

    return prompt | llm | StrOutputParser()


def build_chains(db, llm, db_type):
    return (
        build_sql_chain(db, llm, db_type),
        build_retry_sql_chain(db, llm, db_type),
        build_nl_chain(llm)
    )