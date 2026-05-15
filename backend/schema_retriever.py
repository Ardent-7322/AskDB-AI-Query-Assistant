"""
backend/schema_retriever.py

Semantic schema retrieval for AskDB.
Embeds each table's schema (DDL + sample rows) into ChromaDB at connect time.
At query time, returns only the top-k most relevant tables instead of the full schema.

Drop-in replacement for db.get_table_info() in chains.py.

Usage:
    retriever = SchemaRetriever(db)
    relevant_schema = retriever.get_relevant_schema("who are the top customers by order value?")
"""

import hashlib
from langchain_community.utilities import SQLDatabase

try:
    import chromadb
    from chromadb.utils import embedding_functions
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False


def _table_chunks(db: SQLDatabase) -> list[dict]:
    """
    Split db.get_table_info() into one chunk per table.
    Each chunk contains the table's DDL + sample rows as a single string.
    Returns list of {"table": name, "text": full_chunk}.
    """
    full_schema = db.get_table_info()
    chunks = []
    current_lines = []
    current_table = None

    for line in full_schema.splitlines():
        stripped = line.strip()

        # Detect start of a new table block
        if stripped.upper().startswith("CREATE TABLE"):
            if current_table and current_lines:
                chunks.append({
                    "table": current_table,
                    "text": "\n".join(current_lines).strip()
                })
            current_lines = [line]
            # Extract table name: CREATE TABLE "orders" ( → orders
            import re
            match = re.search(r'CREATE\s+TABLE\s+["`]?(\w+)["`]?', stripped, re.IGNORECASE)
            current_table = match.group(1) if match else f"table_{len(chunks)}"
        else:
            current_lines.append(line)

    # Don't forget the last table
    if current_table and current_lines:
        chunks.append({
            "table": current_table,
            "text": "\n".join(current_lines).strip()
        })

    return chunks


def _schema_fingerprint(db: SQLDatabase) -> str:
    """Short hash of the full schema — used to detect if DB changed and re-index is needed."""
    return hashlib.md5(db.get_table_info().encode()).hexdigest()[:12]


class SchemaRetriever:
    """
    Indexes the DB schema into ChromaDB (in-memory) and retrieves
    the most relevant tables for a given natural language question.

    Falls back to full db.get_table_info() if ChromaDB is not installed
    or if the DB has fewer tables than top_k (no point filtering).
    """

    def __init__(self, db: SQLDatabase, top_k: int = 3):
        self.db = db
        self.top_k = top_k
        self._collection = None
        self._chunks: list[dict] = []
        self._fingerprint: str = ""
        self._indexed = False

        if not CHROMA_AVAILABLE:
            return

        self._build_index()

    def _build_index(self):
        """Parse schema into per-table chunks and upsert into ChromaDB."""
        self._chunks = _table_chunks(self.db)
        self._fingerprint = _schema_fingerprint(self.db)

        # Fewer tables than top_k → retrieval adds no value, skip indexing
        if len(self._chunks) <= self.top_k:
            return

        client = chromadb.Client()  # in-memory, no disk needed

        # Use the default sentence-transformers embedding model
        # (all-MiniLM-L6-v2, ~22MB, runs locally, no API key needed)
        ef = embedding_functions.DefaultEmbeddingFunction()

        collection_name = f"schema_{self._fingerprint}"

        # Reuse existing collection if already indexed (e.g. LLM reload without DB change)
        try:
            self._collection = client.get_collection(
                name=collection_name,
                embedding_function=ef
            )
            self._indexed = True
            return
        except Exception:
            pass

        self._collection = client.create_collection(
            name=collection_name,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"}
        )

        self._collection.upsert(
            ids=[chunk["table"] for chunk in self._chunks],
            documents=[chunk["text"] for chunk in self._chunks],
        )

        self._indexed = True

    def get_relevant_schema(self, question: str) -> str:
        """
        Returns schema string for the top-k tables most relevant to `question`.
        Falls back to full schema if ChromaDB unavailable or DB is small.
        """
        # Fallback: no ChromaDB, or too few tables to bother filtering
        if not CHROMA_AVAILABLE or not self._indexed or self._collection is None:
            return self.db.get_table_info()

        results = self._collection.query(
            query_texts=[question],
            n_results=min(self.top_k, len(self._chunks))
        )

        matched_tables = results["ids"][0]  # list of table names
        matched_texts = results["documents"][0]  # list of schema chunks

        # Preserve original order from schema (for readability)
        order = {chunk["table"]: i for i, chunk in enumerate(self._chunks)}
        paired = sorted(zip(matched_tables, matched_texts), key=lambda x: order.get(x[0], 999))

        return "\n\n".join(text for _, text in paired)

    def refresh(self):
        """Call this if you reconnect to a different DB without restarting."""
        self._indexed = False
        self._collection = None
        if CHROMA_AVAILABLE:
            self._build_index()

    @property
    def table_count(self) -> int:
        return len(self._chunks)

    @property
    def is_filtering(self) -> bool:
        """True if retrieval is actually filtering (DB has more tables than top_k)."""
        return self._indexed and self._collection is not None