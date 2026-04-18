
# AskDB - AI Query Assistant


I built this because I wanted a faster way to query databases without writing SQL every time. Type a question in plain English, get an answer straight from the database. AskDB does the exact work.

Started as a MySQL project, then extended it to PostgreSQL and SQLite so it can plug into any existing backend - including my own [Go Ecommerce](https://github.com/yourusername/go-ecommerce) project running on PostgreSQL and CricMB which is deployed on Render.

## What it does

Type something like _ "Who are the top 10 customers by order value?"_ and AskDB figures out the right SQL for your schema, runs it, and gives you a plain English answer. No SQL knowledge needed.

It also handles follow-up questions. Ask _"What is his economy rate?"_ after a previous query and it understands the context - but if you switch topics entirely, it treats the new question as fresh. No hallucinated context.

If the generated SQL fails, it automatically tries to fix and re-run it before showing an error.

## Features

- **Natural language → SQL → answer** - full pipeline, one question at a time
- **Conversation memory** - resolves follow-ups like "what about last month?" or "show me his stats" without repeating yourself
- **Smart history** - uses context only when the question is clearly a follow-up, ignores it otherwise
- **Auto-retry on SQL errors** - if the first query fails, the LLM debugs and retries automatically
- **Multi-database** - MySQL, PostgreSQL, SQLite out of the box
- **Multiple LLM providers** - Groq (Llama 3.3 70B, Llama 3.1 8B, Mixtral) and Google Gemini (1.5 Flash, 2.0 Flash, 1.5 Pro)
- **API key security** - keys load from `.env` automatically, no need to paste them in the UI every time
- **Transparent output** - generated SQL and raw DB result always available in expandable sections

## Supported Databases

| Database   | Driver   | Default Port |
| ---------- | -------- | ------------ |
| MySQL      | pymysql  | 3306         |
| PostgreSQL | psycopg2 | 5432         |
| SQLite     | built-in | -            |

## Installation

**1. Clone the repo**

```bash
git clone https://github.com/yourusername/askdb.git
cd askdb
```

**2. Create a virtual environment**

```bash
conda create -n askdb python=3.10 -y
conda activate askdb
```

**3. Install dependencies**

```bash
pip install streamlit langchain langchain-community langchain-core langchain-groq langchain-google-genai pymysql psycopg2-binary python-dotenv pandas
```

**4. Set up API keys**

Create a `.env` file in the root:

```
GROQ_API_KEY=your_groq_api_key_here
GOOGLE_API_KEY=your_google_api_key_here
```

Get a free Groq key at [console.groq.com](https://console.groq.com) - no credit card needed.

## Usage

```bash
python -m streamlit run app.py
```

Then in the browser:

1. Pick your database type in the sidebar and fill in connection details
2. Click **Connect**
3. Choose your LLM provider and model - if the key is in `.env` it loads automatically
4. Click **Load LLM**
5. Ask anything in plain English

The answer comes back as a single sentence. The SQL query and raw result are available below it if you want to verify.

> **Note:** AskDB connects to whatever database you point it at - local or remote. For remote access, make sure your DB is reachable from your machine (cloud-hosted DBs like RDS, Supabase, or Railway work out of the box).

## Architecture

![architecture](./architecture/architecture.svg)


**Components:**

- **SQL chain** - injects the DB schema and conversation history into a prompt, generates a dialect-aware SQL query (handles MySQL backticks vs PostgreSQL double-quotes automatically)
- **Retry chain** - if execution fails, takes the broken query + error message and asks the LLM to fix it
- **Database layer** - LangChain `SQLDatabase` wraps the connection; `db.run()` executes live
- **NL chain** - second LLM call that turns the raw result into a one-sentence human-readable answer
- **Memory layer** - conversation history passed into both chains; LLM decides whether to use it based on whether the question is a follow-up

## Connecting to Go Ecommerce Backend

AskDB connects directly to the PostgreSQL database used by the [Go Ecommerce backend](https://github.com/yourusername/go-ecommerce).

Select **PostgreSQL** in the sidebar and use your Go project's DB credentials:

```
Host:     localhost
Port:     5432
Username: postgres
Password: your_db_password
Database: ecom_db
```

Once connected, you can ask things like:

- "What are the total orders placed today?"
- "Which products have the lowest inventory?"
- "Show me all failed payments this week"
- "Who are the top 10 customers by order value?"
- "What is the average order value by product category?"

No changes needed to the Go backend or the schema - AskDB sits entirely on top.

## Evaluation

AskDB includes a built-in evaluation pipeline powered by RAGAS. It automatically generates test questions from your database schema, runs them through the SQL chain, and scores the results - no manual test cases needed.

Tested across multiple real databases including [CricmB](https://cricmb.onrender.com/) - a ball-by-ball IPL statistics database - and a PostgreSQL ecommerce backend, it consistently hits:

- **SQL correctness** - 1.0 on simple to moderate queries
- **Helpfulness** - 3.4 to 4.5 out of 5 depending on schema complexity

The evaluator also runs per-query error analysis and surfaces recurring patterns - so you know exactly what to fix in the prompt rather than guessing.

## License

MIT - do whatever you want with it.
