import streamlit as st
import os
from dotenv import load_dotenv
from backend.database import connect
from backend.llm import get_llm
from backend.chains import build_chains, clean_query, confidence_badge

load_dotenv()

st.set_page_config(page_title="AskDB", layout="wide")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "db" not in st.session_state:
    st.session_state.db = None
if "sql_chain" not in st.session_state:
    st.session_state.sql_chain = None
if "nl_chain" not in st.session_state:
    st.session_state.nl_chain = None
if "llm_name" not in st.session_state:
    st.session_state.llm_name = None
if "db_type" not in st.session_state:
    st.session_state.db_type = "MySQL"

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.header("Database")
    db_type = st.selectbox("Type", ["MySQL", "PostgreSQL", "SQLite"])
    st.session_state.db_type = db_type

    if db_type == "SQLite":
        database = st.text_input("File path", value="mydb.sqlite3")
        host = port = user = password = ""
    else:
        host     = st.text_input("Host", value="localhost")
        port     = st.text_input("Port", value="5432" if db_type == "PostgreSQL" else "3306")
        user     = st.text_input("Username", value="postgres" if db_type == "PostgreSQL" else "root")
        password = st.text_input("Password", type="password")
        database = st.text_input("Database", value="ecom_db" if db_type == "PostgreSQL" else "text_to_sql")

    if st.button("Connect", use_container_width=True):
        try:
            st.session_state.db = connect(db_type, user, password, host, port, database)
            st.success(f"{db_type} connected")
            st.session_state.sql_chain = st.session_state.nl_chain = None
        except Exception as e:
            st.error(str(e))

    st.divider()
    st.header("LLM")
    provider = st.selectbox("Provider", ["Groq", "Google Gemini"])

    if provider == "Groq":
        model = st.selectbox("Model", ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"])
        api_key = st.text_input("Groq API Key", type="password", value=os.getenv("GROQ_API_KEY", ""))
    else:
        model = st.selectbox("Model", ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"])
        api_key = st.text_input("Google API Key", type="password", value=os.getenv("GOOGLE_API_KEY", ""))

    if st.button("Load LLM", use_container_width=True):
        try:
            llm = get_llm(provider, model, api_key)
            if st.session_state.db:
                st.session_state.sql_chain, st.session_state.nl_chain = build_chains(
                    st.session_state.db, llm, st.session_state.db_type)
                st.session_state.llm_name = f"{provider} / {model}"
                st.success("LLM loaded")
            else:
                st.warning("Connect to database first.")
        except Exception as e:
            st.error(str(e))

    if st.session_state.llm_name:
        st.caption(f"Active: {st.session_state.llm_name}")

    st.divider()
    if st.button("Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# ── Main ──────────────────────────────────────────────────────
st.title("AskDB")
st.caption("Ask questions in plain English and get results from your database.")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if msg.get("nl_answer"):
            st.write(msg["nl_answer"])
        if msg.get("confidence"):
            color, label = msg["confidence"]
            st.markdown(f":{color}[{label}]")
        if msg.get("sql"):
            with st.expander("View SQL"):
                st.code(msg["sql"], language="sql")
        if msg.get("raw_result"):
            with st.expander("View Raw Result"):
                st.write(msg["raw_result"])

user_input = st.chat_input("Ask a question about your database...")

if user_input:
    if not st.session_state.sql_chain or not st.session_state.db:
        st.warning("Connect to a database and load an LLM first.")
    else:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.spinner("Thinking..."):
            try:
                query = clean_query(st.session_state.sql_chain.invoke({"question": user_input}))
                try:
                    result = st.session_state.db.run(query)
                    result_text = result if result else "(no rows returned)"
                except Exception as db_err:
                    result_text = f"Query error: {db_err}"

                nl_answer = st.session_state.nl_chain.invoke({
                    "question": user_input, "query": query, "result": result_text
                })

                st.session_state.messages.append({
                    "role": "assistant", "content": "",
                    "nl_answer": nl_answer,
                    "confidence": confidence_badge(result_text),
                    "sql": query, "raw_result": result_text
                })
            except Exception as e:
                st.session_state.messages.append({
                    "role": "assistant", "content": "",
                    "nl_answer": f"Error: {e}",
                    "confidence": ("red", "Low confidence — query failed")
                })
        st.rerun()