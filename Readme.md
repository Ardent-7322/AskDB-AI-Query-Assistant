# AskDB Chatbot - (AI query assistant)

I built this project to solve a problem I kept seeing - people on the team had questions about the data but had to wait for someone technical to pull a report. This chatbot removes that bottleneck entirely. Type a question in plain English, get an answer straight from the database.

It started as a MySQL project but I extended it to support PostgreSQL and SQLite too, which makes it easy to plug into any existing backend - including my own [Go Ecommerce](https://github.com/yourusername/go-ecommerce) project that runs on PostgreSQL.

---

## Table of Contents

- [Project Overview](#project-overview)
- [Features](#features)
- [Supported Databases](#supported-databases)
- [Installation](#installation)
- [Usage](#usage)
- [Architecture](#architecture)
- [Connecting to Go Ecommerce Backend](#connecting-to-go-ecommerce-backend)
- [Future Work](#future-work)
- [License](#license)

---

## Project Overview

In most companies, data lives in SQL databases but most of the team can't query it directly. You end up with a bottleneck where a handful of people handle all the data requests. This chatbot removes that bottleneck.

Type something like _"What are the total orders placed this week?"_ and it handles everything — figures out the right SQL query for your schema, runs it, and gives you a plain English answer. No SQL knowledge needed.

Works across MySQL, PostgreSQL, and SQLite — so it connects directly to existing backends without any schema changes.

---

## Features

- **Natural language to SQL** -> LLM reads your schema and writes accurate queries based on your question
- **Natural language output** -> results come back as a plain one-sentence answer, not raw database tuples
- **Multi-database support** -> MySQL, PostgreSQL, SQLite all work out of the box
- **Multiple LLM support** -> switch between Groq (Llama 3.3 70B, Gemma2, Mixtral) and Google Gemini (1.5 Flash, 2.0 Flash, 1.5 Pro) from the sidebar
- **Streamlit web interface** -> browser-based UI, no terminal needed for end users
- **SQL + raw result visible** -> generated query and raw DB output available in expandable sections for transparency

---

## Supported Databases

| Database   | Driver   | Default Port |
| ---------- | -------- | ------------ |
| MySQL      | pymysql  | 3306         |
| PostgreSQL | psycopg2 | 5432         |
| SQLite     | built-in | —            |

---

## Installation

**1. Clone the repository**

```bash
git clone https://github.com/yourusername/text-to-sql-chatbot.git
cd text-to-sql-chatbot
```

**2. Set up a virtual environment**

```bash
conda create -n text2sql python=3.10 -y
conda activate text2sql
```

**3. Install dependencies**

```bash
pip install streamlit langchain langchain-community langchain-core langchain-groq langchain-google-genai pymysql psycopg2-binary python-dotenv pandas
```

**4. Set up your API keys**

Create a `.env` file in the project root:

```
GROQ_API_KEY=your_groq_api_key_here
GOOGLE_API_KEY=your_google_api_key_here
```

Get a free Groq API key at [console.groq.com](https://console.groq.com).

---

## Usage

```bash
python -m streamlit run app.py
```

Then in the browser:

1. Select your database type (MySQL / PostgreSQL / SQLite) in the sidebar
2. Fill in connection credentials and click **Connect**
3. Choose your LLM provider and model, paste your API key, click **Load LLM**
4. Type your question in the chat box and hit Enter
5. You get a plain English answer with the SQL query and raw result available below

---

## Architecture

```
Excel / existing DB
        │
        ▼
   Pre-process
        │
        ▼
   MySQL / PostgreSQL / SQLite
        │
        ▼ (runtime)
──────────────────────────────────────────────
User question
        │
        ▼
┌───────────────────────────────────────────┐
│              SQL Chain                    │
│  Prompt → Schema → LLM → Parser → SQL     │
└───────────────────────┬───────────────────┘
                        │
                        ▼
              Database  (db.run)
                        │
                        ▼
┌───────────────────────────────────────────┐
│              NL Chain                     │
│  Prompt + result → LLM → Parser           │
└───────────────────────┬───────────────────┘
                        │
                        ▼
            Plain English answer
──────────────────────────────────────────────
```

**Components:**

- **SQL chain** -> LangChain chain that injects the database schema into a prompt and generates a dialect-aware SQL query (MySQL backticks vs PostgreSQL double-quotes handled automatically)
- **Database layer** -> LangChain `SQLDatabase` wraps the connection; `db.run()` executes the query live
- **NL chain** -> second LLM call that takes the question + query + raw result and writes a one-sentence human-readable answer
- **LLM layer** -> supports Groq and Google Gemini, switchable without restarting the app

---

## Connecting to Go Ecommerce Backend

This project connects directly to the PostgreSQL database used by the [Go Ecommerce backend](https://github.com/yourusername/go-ecommerce).

In the sidebar, select **PostgreSQL** and use the same credentials from your Go project's `.env`:

```
Host:     localhost
Port:     5432
Username: postgres
Password: your_db_password
Database: ecom_db
```

Once connected you can ask things like:

- "What are the total orders placed today?"
- "Which products have the lowest inventory?"
- "Show me all failed payments this week"
- "Who are the top 10 customers by order value?"
- "What is the average order value by product category?"

No changes needed to the Go backend or the PostgreSQL schema - this layer sits entirely on top.

---

## Future Work

- **Conversation memory** - right now each question is independent; adding memory would let users ask follow-ups like "what about last month?"
- **Cloud deployment** - package for Streamlit Cloud or Docker so teams can use it without local setup
- **Query history export** - let users download a log of questions and the SQL generated
- **More databases** - MS SQL Server, BigQuery support

---

## License

MIT License. See the LICENSE file for details.

---

Questions or issues? Open a GitHub issue or reach out directly. Contributions welcome.
