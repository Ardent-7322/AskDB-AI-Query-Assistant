import streamlit as st
import os
from dotenv import load_dotenv
from backend.database import connect
from backend.llm import get_llm
from backend.chains import build_chains, clean_query, confidence_badge, format_history

load_dotenv()

st.set_page_config(page_title="AskDB", layout="wide", page_icon="🗄️")

# Load CSS
def load_css(path):
    with open(path) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
load_css("style.css")

# Session state init for messages, db connection, chains, etc.
if "messages" not in st.session_state:
    st.session_state.messages = []
if "db" not in st.session_state:
    st.session_state.db = None
if "sql_chain" not in st.session_state:
    st.session_state.sql_chain = None
if "retry_chain" not in st.session_state:
    st.session_state.retry_chain = None
if "nl_chain" not in st.session_state:
    st.session_state.nl_chain = None
if "llm_name" not in st.session_state:
    st.session_state.llm_name = None
if "db_type" not in st.session_state:
    st.session_state.db_type = "MySQL"

# Sidebar for DB connection and LLM configuration
with st.sidebar:
    st.header("🗄️ Database")
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
            st.success(f"✅ {db_type} connected")
            st.session_state.sql_chain = st.session_state.nl_chain = st.session_state.retry_chain = None
        except Exception as e:
            st.error(str(e))

    st.divider()
    st.header("🤖 LLM")
    provider = st.selectbox("Provider", ["Groq", "Google Gemini", "Anthropic Claude"])

    if provider == "Groq":
        model = st.selectbox("Model", ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"])
        env_key = os.getenv("GROQ_API_KEY", "")
        if env_key:
            st.success("✅ Groq API key loaded from .env")
            api_key = env_key
        else:
            api_key = st.text_input("Groq API Key", type="password", help="Or set GROQ_API_KEY in your .env file")

    elif provider == "Google Gemini":
        model = st.selectbox("Model", ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"])
        env_key = os.getenv("GOOGLE_API_KEY", "")
        if env_key:
            st.success("✅ Google API key loaded from .env")
            api_key = env_key
        else:
            api_key = st.text_input("Google API Key", type="password", help="Or set GOOGLE_API_KEY in your .env file")

    elif provider == "Anthropic Claude":
        model = st.selectbox("Model", ["claude-sonnet-4-5", "claude-opus-4-5", "claude-haiku-4-5-20251001"])
        env_key = os.getenv("ANTHROPIC_API_KEY", "")
        if env_key:
            st.success("✅ Anthropic API key loaded from .env")
            api_key = env_key
        else:
            api_key = st.text_input("Anthropic API Key", type="password", help="Or set ANTHROPIC_API_KEY in your .env file")

    if st.button("Load LLM", use_container_width=True):
        if not api_key:
            st.error("API key missing. Add it in sidebar or set it in your .env file.")
        else:
            try:
                llm = get_llm(provider, model, api_key)
                if st.session_state.db:
                    sql_chain, retry_chain, nl_chain = build_chains(
                        st.session_state.db, llm, st.session_state.db_type)
                    st.session_state.sql_chain   = sql_chain
                    st.session_state.retry_chain = retry_chain
                    st.session_state.nl_chain    = nl_chain
                    st.session_state.llm_name    = f"{provider} / {model}"
                    st.success("✅ LLM loaded")
                else:
                    st.warning("Connect to database first.")
            except Exception as e:
                st.error(str(e))

    if st.session_state.llm_name:
        st.caption(f"Active: {st.session_state.llm_name}")

    st.divider()
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# Main interface for chat and displaying messages
st.markdown("""
<div class="askdb-header">
    <div class="askdb-logo">🗄️</div>
    <div>
        <div class="askdb-title">Ask<span>DB</span></div>
        <div class="askdb-subtitle">Ask questions in plain English and get results from your database.</div>
    </div>
</div>
""", unsafe_allow_html=True)

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if msg.get("nl_answer"):
            st.write(msg["nl_answer"])
        if msg.get("retried"):
            st.info("⚠️ First query failed — auto-corrected and retried.")
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
        history_str = format_history(st.session_state.messages[:-1])

        with st.spinner("Thinking..."):
            try:
                query = clean_query(st.session_state.sql_chain.invoke({
                    "question": user_input,
                    "history":  history_str
                }))

                retried = False

                try:
                    result      = st.session_state.db.run(query)
                    result_text = result if result else "(no rows returned)"
                except Exception as db_err:
                    try:
                        fixed_query = clean_query(st.session_state.retry_chain.invoke({
                            "question":     user_input,
                            "failed_query": query,
                            "error":        str(db_err)
                        }))
                        result      = st.session_state.db.run(fixed_query)
                        result_text = result if result else "(no rows returned)"
                        query       = fixed_query
                        retried     = True
                    except Exception as retry_err:
                        result_text = f"Query error: {retry_err}"

                nl_answer = st.session_state.nl_chain.invoke({
                    "question": user_input,
                    "query":    query,
                    "result":   result_text,
                    "history":  history_str
                })

                st.session_state.messages.append({
                    "role":       "assistant",
                    "content":    "",
                    "nl_answer":  nl_answer,
                    "retried":    retried,
                    "confidence": confidence_badge(result_text),
                    "sql":        query,
                    "raw_result": result_text
                })

            except Exception as e:
                st.session_state.messages.append({
                    "role":       "assistant",
                    "content":    "",
                    "nl_answer":  f"Something went wrong: {e}",
                    "confidence": ("red", "Low confidence — query failed")
                })

        st.rerun()