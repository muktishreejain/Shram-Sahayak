from __future__ import annotations

from functools import lru_cache

from .config import CHROMA_DIR, COLLECTION_NAME, EMBED_MODEL, ensure_dirs


@lru_cache(maxsize=1)
def _embedding_fn():
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    return SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)


def get_collection():
    import chromadb

    ensure_dirs()
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=_embedding_fn(),
    )


def query_chunks(text: str, k: int = 5) -> list[dict]:
    query = (text or "").strip()
    if not query:
        return []
    collection = get_collection()
    if collection.count() == 0:
        return []
    result = collection.query(
        query_texts=[query],
        n_results=min(k, max(collection.count(), 1)),
        include=["documents", "metadatas", "distances"],
    )
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    chunks = []
    for doc, meta in zip(docs, metas):
        meta = meta or {}
        chunks.append(
            {
                "text": doc or "",
                "title": meta.get("title", ""),
                "source_url": meta.get("source_url", ""),
                "topic": meta.get("topic", ""),
            }
        )
    return chunks
