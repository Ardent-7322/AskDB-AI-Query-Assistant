import os
import pandas as pd
from dotenv import load_dotenv
from backend.database import connect
from backend.llm import get_llm
from backend.chains import build_sql_chain, clean_query

load_dotenv()

# ── Config — edit these ───────────────────────────────────────
DB_TYPE   = "MySQL"
HOST      = "localhost"
PORT      = "3306"
USER      = "root"
PASSWORD  = "pass123"
DATABASE  = "text_to_sql"

SQL_PROVIDER = "Groq"
SQL_MODEL    = "llama-3.3-70b-versatile"
SQL_API_KEY  = os.getenv("GROQ_API_KEY")

EVAL_MODEL   = "llama-3.3-70b-versatile"
EVAL_API_KEY = os.getenv("GROQ_API_KEY")

QUESTIONS = [
    "What was the budget of Product 12?",
    "What are the names of all products?",
    "List all customer names.",
    "Find the name and state of all regions.",
    "What is the name of the customer with Customer Index 1?",
]

REFERENCES = [
    "SELECT `2017 Budgets` FROM `2017_budgets` WHERE `Product Name` = 'Product 12';",
    "SELECT `Product Name` FROM products;",
    "SELECT `Customer Names` FROM customers;",
    "SELECT name, state FROM regions;",
    "SELECT `Customer Names` FROM customers WHERE `Customer Index` = 1;",
]

# ── Run evaluation ────────────────────────────────────────────
def run():
    from ragas.metrics import AspectCritic, RubricsScore
    from ragas.dataset_schema import SingleTurnSample, EvaluationDataset
    from ragas import evaluate
    from langchain_groq import ChatGroq
    from ragas.llms import LangchainLLMWrapper

    print("Connecting to database...")
    db = connect(DB_TYPE, USER, PASSWORD, HOST, PORT, DATABASE)
    context = db.get_table_info()

    print("Loading SQL LLM...")
    llm = get_llm(SQL_PROVIDER, SQL_MODEL, SQL_API_KEY)
    sql_chain = build_sql_chain(db, llm, DB_TYPE)

    print("Generating SQL for test questions...")
    responses = []
    for i, q in enumerate(QUESTIONS):
        query = clean_query(sql_chain.invoke({"question": q}))
        responses.append(query)
        print(f"  [{i+1}/{len(QUESTIONS)}] {q}")
        print(f"         → {query}")

    print("\nLoading evaluator LLM...")
    evaluator_llm = LangchainLLMWrapper(
        ChatGroq(model=EVAL_MODEL, api_key=EVAL_API_KEY, temperature=0)
    )

    print("Running RAGAS evaluation...")
    dataset = EvaluationDataset(samples=[
        SingleTurnSample(
            user_input=QUESTIONS[i],
            retrieved_contexts=[context],
            response=responses[i],
            reference=REFERENCES[i],
        ) for i in range(len(QUESTIONS))
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
                llm=evaluator_llm
            ),
        ],
        dataset=dataset
    )

    df = result.to_pandas()
    display_df = pd.DataFrame({
        "Question":      QUESTIONS,
        "Generated SQL": responses,
        "Reference SQL": REFERENCES,
    })
    for col in df.select_dtypes(include="number").columns:
        display_df[col] = df[col].values

    print("\n── Results ──────────────────────────────────")
    print(display_df.to_string(index=False))
    print("\n── Averages ─────────────────────────────────")
    for col in df.select_dtypes(include="number").columns:
        print(f"  {col}: {round(df[col].mean(), 3)}")

    display_df.to_csv("ragas_eval_results.csv", index=False)
    print("\nSaved to ragas_eval_results.csv")

if __name__ == "__main__":
    run()