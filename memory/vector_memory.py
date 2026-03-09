"""
Melvin God Mode - Vector Memory
Supports ChromaDB and Qdrant backends for semantic storage and retrieval.
"""

import uuid
from typing import Optional


def _make_embedding_function(method: str = "sentence-transformers", model: str = "all-MiniLM-L6-v2", ollama_host: str = "http://localhost:11434"):
    """Factory that returns a callable embedding function."""
    if method == "ollama":
        return _OllamaEmbedder(model=model, host=ollama_host)
    # Default: sentence-transformers
    return _SentenceTransformerEmbedder(model=model)


class _SentenceTransformerEmbedder:
    """Wraps sentence-transformers for embedding generation."""

    def __init__(self, model: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(model)
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for the default embedder. "
                "Install with: pip install sentence-transformers"
            )

    def __call__(self, texts: list) -> list:
        return self._model.encode(texts, show_progress_bar=False).tolist()

    def embed_one(self, text: str) -> list:
        return self([text])[0]


class _OllamaEmbedder:
    """Calls the Ollama /api/embeddings endpoint."""

    def __init__(self, model: str = "nomic-embed-text", host: str = "http://localhost:11434"):
        self._model = model
        self._host = host.rstrip("/")
        try:
            import requests
            self._requests = requests
        except ImportError:
            raise ImportError("requests is required for OllamaEmbedder. pip install requests")

    def embed_one(self, text: str) -> list:
        resp = self._requests.post(
            f"{self._host}/api/embeddings",
            json={"model": self._model, "prompt": text},
        )
        resp.raise_for_status()
        return resp.json()["embedding"]

    def __call__(self, texts: list) -> list:
        return [self.embed_one(t) for t in texts]


# ---------------------------------------------------------------------------
# ChromaDB backend
# ---------------------------------------------------------------------------

class _ChromaBackend:
    def __init__(self, collection_name: str, persist_dir: str, embedder):
        try:
            import chromadb
        except ImportError:
            raise ImportError("chromadb is required. pip install chromadb")

        self._embedder = embedder
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def store(self, text: str, metadata: dict) -> str:
        doc_id = str(uuid.uuid4())
        embedding = self._embedder.embed_one(text)
        self._collection.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[metadata],
        )
        return doc_id

    def retrieve(self, query: str, n_results: int = 5) -> list:
        embedding = self._embedder.embed_one(query)
        results = self._collection.query(
            query_embeddings=[embedding],
            n_results=min(n_results, self._collection.count() or 1),
            include=["documents", "metadatas", "distances"],
        )
        output = []
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]
        for text, meta, dist in zip(docs, metas, dists):
            output.append({"text": text, "metadata": meta, "score": 1.0 - dist})
        return output

    def delete(self, doc_id: str) -> bool:
        try:
            self._collection.delete(ids=[doc_id])
            return True
        except Exception:
            return False

    def clear(self):
        self._collection.delete(where={"_id": {"$ne": ""}})  # delete all
        # Safer fallback: recreate the collection
        try:
            client = self._collection._client  # type: ignore
            name = self._collection.name
            client.delete_collection(name)
            self._collection = client.get_or_create_collection(
                name=name, metadata={"hnsw:space": "cosine"}
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Qdrant backend
# ---------------------------------------------------------------------------

class _QdrantBackend:
    def __init__(self, collection_name: str, host: str, port: int, embedder):
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams, PointStruct
        except ImportError:
            raise ImportError("qdrant-client is required. pip install qdrant-client")

        from qdrant_client.models import Distance, VectorParams, PointStruct  # noqa: F811
        self._PS = PointStruct
        self._embedder = embedder
        self._collection_name = collection_name
        self._client = QdrantClient(host=host, port=port)

        # Determine vector size by probing the embedder
        sample_vec = embedder.embed_one("probe")
        vector_size = len(sample_vec)

        existing = [c.name for c in self._client.get_collections().collections]
        if collection_name not in existing:
            self._client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )

    def store(self, text: str, metadata: dict) -> str:
        doc_id = str(uuid.uuid4())
        embedding = self._embedder.embed_one(text)
        payload = {"text": text, **metadata}
        self._client.upsert(
            collection_name=self._collection_name,
            points=[self._PS(id=doc_id, vector=embedding, payload=payload)],
        )
        return doc_id

    def retrieve(self, query: str, n_results: int = 5) -> list:
        embedding = self._embedder.embed_one(query)
        hits = self._client.search(
            collection_name=self._collection_name,
            query_vector=embedding,
            limit=n_results,
        )
        output = []
        for hit in hits:
            payload = dict(hit.payload or {})
            text = payload.pop("text", "")
            output.append({"text": text, "metadata": payload, "score": hit.score})
        return output

    def delete(self, doc_id: str) -> bool:
        try:
            from qdrant_client.models import PointIdsList
            self._client.delete(
                collection_name=self._collection_name,
                points_selector=PointIdsList(points=[doc_id]),
            )
            return True
        except Exception:
            return False

    def clear(self):
        self._client.delete_collection(self._collection_name)
        # Recreate empty collection
        from qdrant_client.models import Distance, VectorParams
        sample_vec = self._embedder.embed_one("probe")
        self._client.create_collection(
            collection_name=self._collection_name,
            vectors_config=VectorParams(size=len(sample_vec), distance=Distance.COSINE),
        )


# ---------------------------------------------------------------------------
# Public VectorMemory class
# ---------------------------------------------------------------------------

class VectorMemory:
    """
    Unified vector memory abstraction supporting ChromaDB and Qdrant backends.

    config keys:
        backend          : "chromadb" (default) | "qdrant"
        collection_name  : str  (default: "melvin_memory")
        persist_dir      : str  (chromadb only, default: "./chroma_db")
        qdrant_host      : str  (qdrant only,   default: "localhost")
        qdrant_port      : int  (qdrant only,   default: 6333)
        embedder         : "sentence-transformers" (default) | "ollama"
        embed_model      : str  embedding model name
        ollama_host      : str  (ollama embedder only)
    """

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        backend = config.get("backend", "chromadb")
        collection_name = config.get("collection_name", "melvin_memory")
        embed_method = config.get("embedder", "sentence-transformers")
        embed_model = config.get("embed_model", "all-MiniLM-L6-v2")
        ollama_host = config.get("ollama_host", "http://localhost:11434")

        self._embedder = _make_embedding_function(embed_method, embed_model, ollama_host)

        if backend == "qdrant":
            qdrant_host = config.get("qdrant_host", "localhost")
            qdrant_port = int(config.get("qdrant_port", 6333))
            self._backend = _QdrantBackend(
                collection_name=collection_name,
                host=qdrant_host,
                port=qdrant_port,
                embedder=self._embedder,
            )
        else:
            persist_dir = config.get("persist_dir", "./chroma_db")
            self._backend = _ChromaBackend(
                collection_name=collection_name,
                persist_dir=persist_dir,
                embedder=self._embedder,
            )

    def store(self, text: str, metadata: Optional[dict] = None) -> str:
        """Store *text* with optional *metadata*. Returns the generated id."""
        return self._backend.store(text, metadata or {})

    def retrieve(self, query: str, n_results: int = 5) -> list:
        """
        Retrieve the *n_results* most relevant documents for *query*.
        Returns list of dicts: {text, metadata, score}.
        """
        return self._backend.retrieve(query, n_results=n_results)

    def delete(self, doc_id: str) -> bool:
        """Delete document by id. Returns True on success."""
        return self._backend.delete(doc_id)

    def clear(self):
        """Remove all documents from the collection."""
        self._backend.clear()
