import os
import json
import pandas as pd
from dotenv import load_dotenv
from backend.database import connect
from backend.llm import get_llm
from backend.chains import build_sql_chain, clean_query

load_dotenv()

#  Config — edit these or set in .env file
DB_TYPE  = "PostgreSQL"
HOST     = "localhost"
PORT     = "5433"
USER     = "postgres"
PASSWORD = "pass123"
DATABASE = "cricmb"

SQL_PROVIDER = "Groq"
SQL_MODEL    = "llama-3.3-70b-versatile"
SQL_API_KEY  = os.getenv("GROQ_API_KEY")

EVAL_MODEL   = "llama-3.3-70b-versatile"
EVAL_API_KEY = os.getenv("GROQ_API_KEY")

NUM_QUESTIONS = 10  # how many questions to auto-generate


# Step 1: Auto-generate questions + reference SQL    
def generate_questions(schema: str, llm, n: int) -> list[dict]:
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser

    prompt = ChatPromptTemplate.from_template("""
You are a database expert. Given the schema below, generate {n} diverse evaluation questions
and their correct reference SQL queries.

Rules:
- Cover different tables and query types (SELECT, WHERE, JOIN, COUNT, GROUP BY, ORDER BY)
- Mix simple and slightly complex queries
- Use exact column and table names from the schema
- Do NOT use LIMIT in reference SQL
- Return ONLY a valid JSON array, no explanation, no markdown

Format:
[
  {{"question": "...", "sql": "..."}},
  ...
]

SCHEMA:
{schema}
""")

    chain = prompt | llm | StrOutputParser()
    raw = chain.invoke({"schema": schema, "n": n})

    # Clean JSON if LLM wraps in markdown or adds extra text. Be lenient but try to extract valid JSON.
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        pairs = json.loads(raw)
        print(f"  Generated {len(pairs)} question-SQL pairs")
        return pairs
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}")
        print(f"  Raw output: {raw[:300]}")
        return []


# Step 2: Run eval  
def run():
    from ragas.metrics import AspectCritic, RubricsScore
    from ragas.dataset_schema import SingleTurnSample, EvaluationDataset
    from ragas import evaluate
    from langchain_groq import ChatGroq
    from ragas.llms import LangchainLLMWrapper

    print(f"\nConnecting to {DB_TYPE} database '{DATABASE}'...")
    db = connect(DB_TYPE, USER, PASSWORD, HOST, PORT, DATABASE)
    schema = db.get_table_info()
    print("  Connected.")

    print(f"\nLoading LLM ({SQL_PROVIDER} / {SQL_MODEL})...")
    llm = get_llm(SQL_PROVIDER, SQL_MODEL, SQL_API_KEY)
    sql_chain = build_sql_chain(db, llm, DB_TYPE)

    print(f"\nAuto-generating {NUM_QUESTIONS} evaluation questions from schema...")
    pairs = generate_questions(schema, llm, NUM_QUESTIONS)

    if not pairs:
        print("No questions generated. Check your schema or LLM output.")
        return

    questions  = [p["question"] for p in pairs]
    references = [p["sql"] for p in pairs]

    print("\nGenerating SQL for each question...")
    responses = []
    for i, q in enumerate(questions):
        query = clean_query(sql_chain.invoke({
            "question": q,
            "history":  "No previous conversation."
        }))
        responses.append(query)
        print(f"  [{i+1}/{len(questions)}] {q}")
        print(f"           → {query}")

    print("\nLoading evaluator LLM...")
    evaluator_llm = LangchainLLMWrapper(
        ChatGroq(model=EVAL_MODEL, api_key=EVAL_API_KEY, temperature=0)
    )

    print("\nRunning RAGAS evaluation...")
    dataset = EvaluationDataset(samples=[
        SingleTurnSample(
            user_input=questions[i],
            retrieved_contexts=[schema],
            response=responses[i],
            reference=references[i],
        ) for i in range(len(questions))
    ])

    result = evaluate(
        metrics=[
            AspectCritic(
                name="sql_correctness",
                definition="Is the SQL syntactically correct and does it accurately answer the question based on the schema?",
                llm=evaluator_llm,
            ),
            RubricsScore(
                name="helpfulness",
                rubrics={
                    "score1_description": "SQL is completely wrong or irrelevant.",
                    "score2_description": "SQL is partially relevant but has errors.",
                    "score3_description": "SQL is mostly correct but could be improved.",
                    "score4_description": "SQL is correct and answers the question.",
                    "score5_description": "SQL is perfectly correct and optimized.",
                },
                llm=evaluator_llm,
            ),
        ],
        dataset=dataset,
    )

    df = result.to_pandas()

    display_df = pd.DataFrame({
        "Question":      questions,
        "Generated SQL": responses,
        "Reference SQL": references,
    })
    for col in df.select_dtypes(include="number").columns:
        display_df[col] = df[col].values

    print("\n── Results ──────────────────────────────────────────────────")
    print(display_df.to_string(index=False))

    print("\n── Averages ─────────────────────────────────────────────────")
    for col in df.select_dtypes(include="number").columns:
        avg = round(df[col].mean(), 3)
        print(f"  {col}: {avg}")

    out_file = f"ragas_eval_{DATABASE}.csv"
    display_df.to_csv(out_file, index=False)
    print(f"\nSaved to {out_file}")


if __name__ == "__main__":
    run()