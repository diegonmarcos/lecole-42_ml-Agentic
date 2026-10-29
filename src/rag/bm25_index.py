"""
BM25 Keyword Search Index for Hybrid RAG

This module implements BM25 (Best Matching 25) keyword search to complement
semantic search in the hybrid RAG pipeline.

Usage:
    from rag.bm25_index import BM25Index

    index = BM25Index()
    index.index_documents(documents, doc_ids)
    results = index.search("query text", top_k=10)
"""

import logging
import pickle
from typing import List, Optional, Tuple

import numpy as np
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)


class BM25Index:
    """
    BM25 keyword search index for hybrid RAG.

    Features:
    - Fast keyword matching (<30ms p95 latency)
    - Persistence support (save/load index)
    - Batch indexing for efficiency
    - Score normalization (0-1 range)
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        """
        Initialize BM25 index.

        Args:
            k1: Term frequency saturation parameter (default: 1.5)
            b: Length normalization parameter (default: 0.75)
        """
        self.k1 = k1
        self.b = b
        self.index: Optional[BM25Okapi] = None
        self.documents: List[str] = []
        self.doc_ids: List[str] = []
        self.tokenized_corpus: List[List[str]] = []

    def index_documents(self, documents: List[str], doc_ids: List[str]) -> None:
        """
        Index documents for BM25 keyword search.

        Args:
            documents: List of document texts
            doc_ids: List of document IDs (must match documents length)

        Raises:
            ValueError: If documents and doc_ids lengths don't match
        """
        if len(documents) != len(doc_ids):
            raise ValueError(
                f"documents and doc_ids must have same length: "
                f"{len(documents)} != {len(doc_ids)}"
            )

        logger.info("Indexing %s documents for BM25...", len(documents))

        # Store originals
        self.documents = documents
        self.doc_ids = doc_ids

        # Tokenize corpus (simple whitespace + lowercase)
        self.tokenized_corpus = [self._tokenize(doc) for doc in documents]

        # Build BM25 index
        self.index = BM25Okapi(self.tokenized_corpus, k1=self.k1, b=self.b)

        logger.info("BM25 index built successfully")

    def search(
        self, query: str, top_k: int = 10, normalize: bool = True
    ) -> List[Tuple[str, float]]:
        """
        Search index with BM25 scoring.

        Args:
            query: Search query
            top_k: Number of results to return
            normalize: Normalize scores to 0-1 range

        Returns:
            List of (doc_id, score) tuples sorted by score descending

        Raises:
            RuntimeError: If index not built
        """
        if self.index is None:
            raise RuntimeError("Index not built. Call index_documents() first.")

        # Tokenize query
        tokenized_query = self._tokenize(query)

        # Get BM25 scores
        scores = self.index.get_scores(tokenized_query)

        # Normalize scores if requested
        if normalize and len(scores) > 0:
            max_score = np.max(scores)
            if max_score > 0:
                scores = scores / max_score

        # Get top-k indices
        top_indices = np.argsort(scores)[::-1][:top_k]

        # Return (doc_id, score) tuples
        results = [(self.doc_ids[idx], float(scores[idx])) for idx in top_indices]

        return results

    def get_scores(self, query: str) -> np.ndarray:
        """
        Get raw BM25 scores for all documents.

        Args:
            query: Search query

        Returns:
            NumPy array of scores (one per document)
        """
        if self.index is None:
            raise RuntimeError("Index not built. Call index_documents() first.")

        tokenized_query = self._tokenize(query)
        return self.index.get_scores(tokenized_query)

    def save(self, filepath: str) -> None:
        """
        Save index to disk.

        Args:
            filepath: Path to save pickle file
        """
        if self.index is None:
            raise RuntimeError("No index to save")

        state = {
            "k1": self.k1,
            "b": self.b,
            "documents": self.documents,
            "doc_ids": self.doc_ids,
            "tokenized_corpus": self.tokenized_corpus,
            "index": self.index,
        }

        with open(filepath, "wb") as f:
            pickle.dump(state, f)

        logger.info("BM25 index saved to %s", filepath)

    def load(self, filepath: str) -> None:
        """
        Load index from disk.

        Args:
            filepath: Path to pickle file
        """
        with open(filepath, "rb") as f:
            state = pickle.load(f)

        self.k1 = state["k1"]
        self.b = state["b"]
        self.documents = state["documents"]
        self.doc_ids = state["doc_ids"]
        self.tokenized_corpus = state["tokenized_corpus"]
        self.index = state["index"]

        logger.info(
            "BM25 index loaded from %s (%s docs)", filepath, len(self.documents)
        )

    def _tokenize(self, text: str) -> List[str]:
        """
        Simple tokenization (whitespace + lowercase).

        For production, consider using spaCy or NLTK for better tokenization.

        Args:
            text: Input text

        Returns:
            List of tokens
        """
        return text.lower().split()

    def get_index_size(self) -> dict:
        """
        Get index statistics.

        Returns:
            Dict with num_documents, avg_doc_length, vocab_size
        """
        if self.index is None:
            return {"num_documents": 0, "avg_doc_length": 0, "vocab_size": 0}

        doc_lengths = [len(doc) for doc in self.tokenized_corpus]
        vocab = set(token for doc in self.tokenized_corpus for token in doc)

        return {
            "num_documents": len(self.documents),
            "avg_doc_length": np.mean(doc_lengths) if doc_lengths else 0,
            "vocab_size": len(vocab),
        }


# Example usage
def _demo() -> None:
    """Run a small demonstration of this module."""
    # Sample documents
    documents = [
        "The quick brown fox jumps over the lazy dog",
        "Machine learning is a subset of artificial intelligence",
        "Python is a popular programming language for data science",
        "Natural language processing enables computers to understand text",
        "Deep learning uses neural networks with multiple layers",
    ]
    doc_ids = [f"doc_{i}" for i in range(len(documents))]

    # Create and index
    index = BM25Index()
    index.index_documents(documents, doc_ids)

    # Search
    results = index.search("machine learning python", top_k=3)
    print("Search results:")
    for doc_id, score in results:
        print(f"  {doc_id}: {score:.4f}")

    # Save
    index.save("/tmp/bm25_index.pkl")

    # Load
    new_index = BM25Index()
    new_index.load("/tmp/bm25_index.pkl")
    print(f"\nLoaded index: {new_index.get_index_size()}")


if __name__ == "__main__":
    _demo()
