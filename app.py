import streamlit as st
import os
import pandas as pd
from dotenv import load_dotenv
from backend.database import connect
from backend.llm import get_llm
from backend.chains import build_chains, clean_query, confidence_badge, format_history

load_dotenv()

st.set_page_config(page_title="AskDB", layout="wide", page_icon="assets/favicon.ico")

def load_css(path):
    with open(path) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
load_css("style.css")

# ── Session state init ─────────────────────────────────────────
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
if "connected_db_name" not in st.session_state:
    st.session_state.connected_db_name = None

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown("**DATABASE**")

    db_type = st.selectbox("Type", ["MySQL", "PostgreSQL", "SQLite"], label_visibility="collapsed")
    st.session_state.db_type = db_type

    if db_type == "SQLite":
        database = st.text_input("File path", value="mydb.sqlite3", placeholder="path/to/file.sqlite3")
        host = port = user = password = ""
    else:
        host     = st.text_input("Host", value="localhost", placeholder="localhost")
        port     = st.text_input("Port", value="5432" if db_type == "PostgreSQL" else "3306")
        user     = st.text_input("Username", value="postgres" if db_type == "PostgreSQL" else "root")
        password = st.text_input("Password", type="password", placeholder="••••••••")
        database = st.text_input("Database", value="ecom_db" if db_type == "PostgreSQL" else "text_to_sql")

    if st.button("Connect", use_container_width=True):
        try:
            st.session_state.db = connect(db_type, user, password, host, port, database)
            st.session_state.connected_db_name = database
            st.session_state.sql_chain = st.session_state.nl_chain = st.session_state.retry_chain = None
            st.rerun()
        except Exception as e:
            st.error(str(e))

    if st.session_state.connected_db_name:
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:6px;background:#0d1f12;border:1px solid #1a3a22;'
            f'border-radius:20px;padding:4px 10px;margin-top:4px;">'
            f'<div style="width:6px;height:6px;border-radius:50%;background:#4ade80;flex-shrink:0"></div>'
            f'<span style="font-family:IBM Plex Mono,monospace;font-size:11px;color:#4ade80">'
            f'Connected · {st.session_state.connected_db_name}</span></div>',
            unsafe_allow_html=True
        )

    st.divider()
    st.markdown("**LLM**")

    provider = st.selectbox("Provider", ["Groq", "Google Gemini", "Anthropic Claude"], label_visibility="collapsed")

    if provider == "Groq":
        model   = st.selectbox("Model", ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"], label_visibility="collapsed")
        env_key = os.getenv("GROQ_API_KEY", "")
        api_key = env_key if env_key else st.text_input("Groq API Key", type="password", placeholder="gsk_...")
        if env_key:
            st.markdown('<span style="font-family:IBM Plex Mono,monospace;font-size:11px;color:#374151">API key from .env</span>', unsafe_allow_html=True)

    elif provider == "Google Gemini":
        model   = st.selectbox("Model", ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"], label_visibility="collapsed")
        env_key = os.getenv("GOOGLE_API_KEY", "")
        api_key = env_key if env_key else st.text_input("Google API Key", type="password", placeholder="AIza...")
        if env_key:
            st.markdown('<span style="font-family:IBM Plex Mono,monospace;font-size:11px;color:#374151">API key from .env</span>', unsafe_allow_html=True)

    elif provider == "Anthropic Claude":
        model   = st.selectbox("Model", ["claude-sonnet-4-5", "claude-opus-4-5", "claude-haiku-4-5-20251001"], label_visibility="collapsed")
        env_key = os.getenv("ANTHROPIC_API_KEY", "")
        api_key = env_key if env_key else st.text_input("Anthropic API Key", type="password", placeholder="sk-ant-...")
        if env_key:
            st.markdown('<span style="font-family:IBM Plex Mono,monospace;font-size:11px;color:#374151">API key from .env</span>', unsafe_allow_html=True)

    if st.button("Load LLM", use_container_width=True):
        if not api_key:
            st.error("API key missing.")
        else:
            try:
                llm = get_llm(provider, model, api_key)
                if st.session_state.db:
                    sql_chain, retry_chain, nl_chain = build_chains(
                        st.session_state.db, llm, st.session_state.db_type)
                    st.session_state.sql_chain   = sql_chain
                    st.session_state.retry_chain = retry_chain
                    st.session_state.nl_chain    = nl_chain
                    st.session_state.llm_name    = f"{provider} · {model}"
                    st.rerun()
                else:
                    st.warning("Connect to a database first.")
            except Exception as e:
                st.error(str(e))

    if st.session_state.llm_name:
        st.markdown(
            f'<span style="font-family:IBM Plex Mono,monospace;font-size:11px;color:#374151">'
            f'{st.session_state.llm_name}</span>',
            unsafe_allow_html=True
        )

    st.divider()
    if st.button("Clear chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()


# ── Header ────────────────────────────────────────────────────
st.markdown("""
<div class="askdb-header">
    <svg class="askdb-logo-icon" viewBox="0 0 62 62" fill="none" xmlns="http://www.w3.org/2000/svg">
        <defs>
            <linearGradient id="g1" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="#60a5fa"/>
                <stop offset="100%" stop-color="#3b82f6"/>
            </linearGradient>
            <linearGradient id="gfill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#3b82f6" stop-opacity="0.12"/>
                <stop offset="100%" stop-color="#3b82f6" stop-opacity="0.03"/>
            </linearGradient>
        </defs>
        <!-- Bottom cylinder -->
        <rect x="11" y="34" width="40" height="14" fill="url(#gfill)"/>
        <ellipse cx="31" cy="48" rx="20" ry="6" stroke="url(#g1)" stroke-width="1.5" fill="none"/>
        <ellipse cx="31" cy="34" rx="20" ry="6" stroke="url(#g1)" stroke-width="1.5" fill="none" stroke-dasharray="3 2"/>
        <line x1="11" y1="34" x2="11" y2="48" stroke="url(#g1)" stroke-width="1.5"/>
        <line x1="51" y1="34" x2="51" y2="48" stroke="url(#g1)" stroke-width="1.5"/>
        <!-- Top cylinder -->
        <rect x="11" y="18" width="40" height="14" fill="url(#gfill)"/>
        <ellipse cx="31" cy="32" rx="20" ry="6" stroke="url(#g1)" stroke-width="1.5" fill="none" stroke-dasharray="3 2"/>
        <ellipse cx="31" cy="18" rx="20" ry="6" stroke="url(#g1)" stroke-width="2" fill="#1e3a5f" fill-opacity="0.4"/>
        <line x1="11" y1="18" x2="11" y2="32" stroke="url(#g1)" stroke-width="1.5"/>
        <line x1="51" y1="18" x2="51" y2="32" stroke="url(#g1)" stroke-width="1.5"/>
        <!-- Query mark -->
        <text x="26.5" y="44" font-family="IBM Plex Mono, monospace" font-weight="500" font-size="13" fill="#60a5fa">?</text>
    </svg>
    <div class="askdb-wordmark">Ask<span class="db">DB</span></div>
</div>
""", unsafe_allow_html=True)


# ── Helper: parse result into dataframe ───────────────────────
def parse_result_to_df(raw_result, query):
    try:
        if not raw_result or raw_result == "(no rows returned)":
            return None, 0
        import ast
        parsed = ast.literal_eval(raw_result)
        if not parsed:
            return None, 0
        import re
        select_match = re.search(r'SELECT\s+(.*?)\s+FROM', query, re.IGNORECASE | re.DOTALL)
        if select_match:
            cols_raw = select_match.group(1)
            cols = [c.strip().split(' ')[-1].replace('"','').replace('`','')
                    for c in cols_raw.split(',')]
        else:
            cols = [f"col_{i+1}" for i in range(len(parsed[0]))]
        if len(cols) != len(parsed[0]):
            cols = [f"col_{i+1}" for i in range(len(parsed[0]))]
        df = pd.DataFrame(parsed, columns=cols)
        return df, len(df)
    except Exception:
        return None, 0


# ── Helper: confidence pill HTML ──────────────────────────────
def render_confidence(confidence_tuple):
    if not confidence_tuple:
        return ""
    color, label = confidence_tuple
    if color == "red":
        return (
            '<div class="conf-pill conf-pill-low">'
            '<div class="conf-dot conf-dot-low"></div>'
            f'{label}</div>'
        )
    return (
        '<div class="conf-pill">'
        '<div class="conf-dot"></div>'
        f'{label}</div>'
    )


# ── Render chat history ───────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.write(msg["content"])
        else:
            if msg.get("nl_answer"):
                st.write(msg["nl_answer"])

            if msg.get("retried"):
                st.markdown(
                    '<div style="font-family:IBM Plex Mono,monospace;font-size:11px;color:#f59e0b;'
                    'margin:4px 0">Auto-corrected query — retried successfully.</div>',
                    unsafe_allow_html=True
                )

            if msg.get("confidence"):
                st.markdown(render_confidence(msg["confidence"]), unsafe_allow_html=True)

            if msg.get("sql"):
                with st.expander("SQL"):
                    st.code(msg["sql"], language="sql")

            if msg.get("raw_result"):
                df, row_count = parse_result_to_df(msg["raw_result"], msg.get("sql", ""))
                label = f"Results · {row_count} row{'s' if row_count != 1 else ''}" if row_count else "Results"
                with st.expander(label):
                    if df is not None:
                        st.dataframe(df, use_container_width=True, hide_index=True)
                    else:
                        st.markdown(
                            f'<span style="font-family:IBM Plex Mono,monospace;font-size:12px;color:#4b5563">'
                            f'{msg["raw_result"]}</span>',
                            unsafe_allow_html=True
                        )


# ── Chat input ────────────────────────────────────────────────
user_input = st.chat_input("Ask anything about your database...")

if user_input:
    if not st.session_state.sql_chain or not st.session_state.db:
        st.warning("Connect to a database and load an LLM first.")
    else:
        st.session_state.messages.append({"role": "user", "content": user_input})
        history_str = format_history(st.session_state.messages[:-1])

        with st.spinner(""):
            try:
                from backend.chains import extract_last_entity
                last_entity = extract_last_entity(st.session_state.messages[:-1])
                query = clean_query(st.session_state.sql_chain.invoke({
                    "question":    user_input,
                    "history":     history_str,
                    "last_entity": last_entity
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
                    "confidence": ("red", "Query failed")
                })

        st.rerun()