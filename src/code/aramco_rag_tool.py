"""
title: Aramco Knowledge Base RAG
author: Munirdin Jadikar
description: Retrieves relevant chunks from the Aramco knowledge base using pgvector similarity search.
required_open_webui_version: 0.3.0
requirements: psycopg2-binary, openai
"""

from pydantic import BaseModel, Field
from typing import Callable, Any
import json


class Tools:
    class Valves(BaseModel):
        OPENAI_API_KEY: str = Field(
            default="",
            description="OpenAI API key (used to embed the query)",
        )
        DB_URL: str = Field(
            default="",
            description="PostgreSQL connection string (Railway)",
        )
        COLLECTION_NAME: str = Field(
            default="2bad0dc7-35d7-48fc-bd2c-7b42ccb2189f",
            description="OpenWebUI knowledge collection UUID",
        )
        EMBEDDING_MODEL: str = Field(
            default="text-embedding-3-small",
            description="OpenAI embedding model — must match what was used to build the index",
        )
        TOP_K: int = Field(
            default=6,
            description="Number of chunks to return",
        )

    def __init__(self):
        self.valves = self.Valves()

    def search_knowledge_base(self, query: str) -> str:
        """
        Search the Saudi Aramco knowledge base for information relevant to the query.
        Use this whenever the user asks about Aramco financials, operations, strategy,
        annual reports, production figures, or any Aramco-specific data.
        :param query: The user's question or search terms.
        :return: Relevant excerpts from the Aramco knowledge base.
        """
        try:
            from openai import OpenAI
            import psycopg2

            # 1. Embed the query
            client = OpenAI(api_key=self.valves.OPENAI_API_KEY)
            response = client.embeddings.create(
                input=[query],
                model=self.valves.EMBEDDING_MODEL,
            )
            query_vector = response.data[0].embedding
            vector_str = "[" + ",".join(str(x) for x in query_vector) + "]"

            # 2. Query pgvector — cosine similarity (lower <=> distance = more similar)
            conn = psycopg2.connect(self.valves.DB_URL, connect_timeout=10)
            cur = conn.cursor()
            cur.execute(
                """
                SELECT text,
                       1 - (vector <=> %s::vector) AS similarity,
                       vmetadata
                FROM document_chunk
                WHERE collection_name = %s
                ORDER BY vector <=> %s::vector
                LIMIT %s
                """,
                (vector_str, self.valves.COLLECTION_NAME, vector_str, self.valves.TOP_K),
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()

            if not rows:
                return "No relevant information found in the Aramco knowledge base."

            # 3. Format results
            parts = [f"### Aramco Knowledge Base — top {len(rows)} results for: '{query}'\n"]
            for i, (text, similarity, meta) in enumerate(rows, 1):
                page = ""
                if meta and isinstance(meta, dict) and "page" in meta:
                    page = f" (chunk {meta['page']})"
                parts.append(f"**[{i}]** (similarity: {similarity:.3f}){page}\n{text.strip()}\n")

            return "\n---\n".join(parts)

        except Exception as e:
            return f"RAG search failed: {e}"
