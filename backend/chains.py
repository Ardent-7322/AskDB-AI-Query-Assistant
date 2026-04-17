import re
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough


def clean_query(raw: str) -> str:
    match = re.search(r"```sql\s*(.*?)\s*```", raw, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else raw.strip().rstrip(";")


def confidence_badge(result_text: str) -> tuple:
    if result_text.startswith("Query error"):
        return "red", "Low confidence"
    elif result_text == "(no rows returned)":
        return "orange", "Medium confidence"
    return "green", "High confidence"


def format_history(messages: list) -> str:
    history = []
    for m in messages:
        if m["role"] == "user":
            history.append(f"User: {m['content']}")
        elif m["role"] == "assistant" and m.get("nl_answer"):
            history.append(f"Assistant: {m['nl_answer']}")
    return "\n".join(history) if history else "No previous conversation."


def extract_last_entity(messages: list) -> str:
    """Extract exact entity from last SQL result for follow-up resolution."""
    for msg in reversed(messages):
        if msg.get("raw_result"):
            text = str(msg["raw_result"]).strip()
            rows = text.split("\n")
            if len(rows) > 1:
                first_cell = rows[1].split("|")[0].strip()
                if first_cell:
                    return first_cell
        if msg.get("nl_answer"):
            return msg["nl_answer"]
    return ""


def get_column_tags(schema: str) -> str:
    """Auto-tag columns by type from schema DDL."""
    tags = []
    for line in schema.split("\n"):
        l = line.strip()
        if not l:
            continue
        if any(t in l.upper() for t in ["INTEGER", "BIGINT", "NUMERIC", "FLOAT", "DOUBLE", "REAL", "DECIMAL"]):
            tags.append(f"  {l} → NUMERIC or BINARY_FLAG (check sample rows to confirm)")
        elif any(t in l.upper() for t in ["TEXT", "VARCHAR", "CHAR"]):
            tags.append(f"  {l} → ENTITY or CATEGORICAL")
        elif "BOOLEAN" in l.upper():
            tags.append(f"  {l} → BINARY_FLAG")
    return "\n".join(tags) if tags else "Infer column types from sample rows."


def build_sql_chain(db, llm, db_type):
    dialect = "PostgreSQL" if db_type == "PostgreSQL" else "SQLite" if db_type == "SQLite" else "MySQL"
    quote_char = '"' if db_type == "PostgreSQL" else "`"

    prompt = ChatPromptTemplate.from_template(f"""
You are an expert {dialect} query generator.

CONVERSATION HISTORY:
{{history}}

LAST ENTITY (extract exact value for follow-up resolution):
{{last_entity}}

SCHEMA WITH SAMPLE ROWS:
{{schema}}

COLUMN TYPE TAGS (auto-detected):
{{column_tags}}

STEP 1 — READ SCHEMA CAREFULLY:
- Use EXACT column names as shown — check case sensitivity
- Look at sample rows to confirm what each column stores
- Identify: ENTITY columns (text, group by these), NUMERIC columns (sum these), BINARY_FLAG columns (0/1 → use SUM not COUNT), UNIT columns (denominator)

STEP 2 — MAP QUESTION TO SQL PATTERN:
- "most/highest/best"   → ORDER BY value DESC LIMIT 1
- "least/lowest/worst"  → ORDER BY value ASC LIMIT 1
- "total"               → SUM(NUMERIC column)
- "how many/count"      → COUNT(DISTINCT entity_col)
- "wickets taken/most wickets" → always GROUP BY bowler column, SUM(bowler_wicket_flag) or COUNT wicket_kind IS NOT NULL — NEVER use batter column for bowling questions
- "runs scored/most runs" → always GROUP BY batter column — NEVER use bowler column for batting questions
- For bowling metrics (economy, wickets, strike rate) → always use the column that identifies the bowler, not the batter
- "average"             → SUM(NUMERIC) / NULLIF(SUM(BINARY_FLAG_event), 0) — ratio of totals, NOT AVG(), NOT dividing by unit/row count
  To find denominator: look for a BINARY_FLAG column in schema whose sample values are 0 or 1 and represents "did the event happen". Use SUM of that column as denominator, not ball count or row count.
- "rate/per over/per unit" → SUM(NUMERIC) * 6.0 / COUNT(*) for economy/run rate — multiply by 6 to convert balls to overs, NEVER divide by 6
- "run rate" / "economy" → always SUM(runs) * 6.0 / COUNT(*) — result should be 6-10 range, not 0.3-1.0 range
- "strike rate (batting)" → SUM(runs) * 100.0 / SUM(balls_faced)
- "strike rate (bowling)" → SUM(UNIT_balls) / NULLIF(SUM(BINARY_FLAG_wicket), 0)
- "percentage"          → SUM(condition) * 100.0 / COUNT(*)
- "sixes"               → filter runs_col = 6, do NOT rely on boundary flag columns

STEP 3 — DENOMINATOR DETECTION:
- For averages: denominator = SUM of BINARY_FLAG column representing the event (dismissal, goal, conversion)
- Always wrap denominator in NULLIF(..., 0) to prevent division by zero
- Never use row count or ball count as denominator for scoring averages

STEP 4 — FOLLOW-UP RESOLUTION:
- Follow-up signals: he, she, his, her, they, it, that, same, those, these
- If follow-up → extract EXACT entity value from LAST ENTITY and use in WHERE clause
- If self-contained question → ignore history

STEP 5 — QUALITY:
- HAVING COUNT(*) >= 240 for bowling stats (= 40 overs minimum) — apply ONLY when comparing multiple entities (GROUP BY without WHERE on specific entity)
- HAVING SUM(balls_faced) >= 200 for batting stats — apply ONLY when comparing multiple entities
- When question is about a SPECIFIC player/team (WHERE name = '...'), do NOT apply minimum threshold — just return their stats
- Player/entity names in DB may be in lowercase abbreviated format (e.g. 'ys chahal', 'v kohli', 'ab de villiers')
- Always use ILIKE instead of = for name matching to handle case insensitivity
- If user says "Yuzvendra Chahal", search using ILIKE '%chahal%' not = 'YS Chahal'
- Extract the last name or most unique part of the name for LIKE matching
- Always use HAVING, never WHERE for aggregate conditions
- HAVING COUNT(DISTINCT match_id) >= 5 for match-level stats
- COUNT(DISTINCT col) when counting unique entities
- Wrap mixed-case or spaced column names in {quote_char}
- Return ONLY raw SQL — no markdown, no explanation, single line

CURRENT QUESTION: {{question}}
SQL:""")

    return (
        RunnablePassthrough.assign(
            schema=lambda _: db.get_table_info(),
            column_tags=lambda _: get_column_tags(db.get_table_info())
        )
        | prompt
        | llm
        | StrOutputParser()
    )


def build_retry_sql_chain(db, llm, db_type):
    dialect = "PostgreSQL" if db_type == "PostgreSQL" else "SQLite" if db_type == "SQLite" else "MySQL"
    quote_char = '"' if db_type == "PostgreSQL" else "`"

    prompt = ChatPromptTemplate.from_template(f"""
You are an expert {dialect} query debugger.

Analyze the error and fix the query. Common issues:
- Wrong column name or wrong case → use exact name from schema
- Wrong aggregation → SUM for values, COUNT for rows, NULLIF for division
- WHERE used instead of HAVING for aggregates
- Missing JOIN condition or wrong join column

Return ONLY the fixed SQL — no markdown, no explanation, single line.

SCHEMA:
{{schema}}

QUESTION: {{question}}
FAILED SQL: {{failed_query}}
ERROR: {{error}}
FIXED SQL:""")

    return (
        RunnablePassthrough.assign(schema=lambda _: db.get_table_info())
        | prompt
        | llm
        | StrOutputParser()
    )


def build_nl_chain(llm):
    prompt = ChatPromptTemplate.from_template("""
Write ONE clear sentence answering the question using actual values from the result.
Include specific names and numbers. No extra explanation.

CONVERSATION HISTORY (use only for follow-ups):
{history}

Question: {question}
SQL: {query}
Result: {result}

Answer:""")

    return prompt | llm | StrOutputParser()


def build_chains(db, llm, db_type):
    return (
        build_sql_chain(db, llm, db_type),
        build_retry_sql_chain(db, llm, db_type),
        build_nl_chain(llm)
    )