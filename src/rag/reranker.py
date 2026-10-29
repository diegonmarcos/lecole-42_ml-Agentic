"""
Reranking Pipeline - Improve search result relevance with cross-encoder

Uses cross-encoder models to rerank initial search results for better precision.
Cross-encoders directly score query-document pairs (vs bi-encoders that compute
separate embeddings).

Benefits:
- 5-15% precision improvement over bi-encoder-only search
- Catches subtle semantic matches missed by vector search
- Works well with hybrid search (BM25 + semantic + reranking)

Performance: ~10-50ms per query depending on model and result count
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)


@dataclass
class RerankResult:
    """Reranked search result"""

    doc_id: str
    text: str
    original_score: float
    rerank_score: float
    final_score: float
    metadata: Optional[Dict] = None


class Reranker:
    """
    Rerank search results using cross-encoder models.

    Usage:
        reranker = Reranker(model="cross-encoder/ms-marco-MiniLM-L-6-v2")

        results = [
            {"id": "doc1", "text": "...", "score": 0.8},
            {"id": "doc2", "text": "...", "score": 0.7},
        ]

        reranked = reranker.rerank(query="what is AI?", results=results, top_k=5)
    """

    # Recommended models by use case
    MODELS = {
        "fast": "cross-encoder/ms-marco-MiniLM-L-2-v2",  # 33M params, ~10ms
        "balanced": "cross-encoder/ms-marco-MiniLM-L-6-v2",  # 33M params, ~20ms
        "accurate": "cross-encoder/ms-marco-TinyBERT-L-6",  # 68M params, ~30ms
        "multilingual": "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",  # 118M params
    }

    def __init__(
        self,
        model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        max_length: int = 512,
        batch_size: int = 32,
        device: Optional[str] = None,
    ):
        """
        Initialize reranker.

        Args:
            model: Cross-encoder model name or path
            max_length: Maximum sequence length (query + document)
            batch_size: Batch size for scoring
            device: Device to use ('cuda' or 'cpu', auto-detect if None)
        """
        self.model_name = model
        self.max_length = max_length
        self.batch_size = batch_size

        # Load cross-encoder
        logger.info("Loading cross-encoder: %s", model)
        self.model = CrossEncoder(model, max_length=max_length, device=device)

        logger.info("Reranker ready (device: %s)", self.model.device)

    def _create_pairs(self, query: str, results: List[Dict]) -> List[Tuple[str, str]]:
        """
        Create query-document pairs for scoring.

        Args:
            query: Search query
            results: List of result dicts with 'text' field

        Returns:
            List of (query, document) tuples
        """
        pairs = []

        for result in results:
            doc_text = result.get("text", "")
            if not doc_text:
                logger.warning("Empty text for result: %s", result.get("id", "unknown"))
                doc_text = ""

            pairs.append((query, doc_text))

        return pairs

    def rerank(
        self,
        query: str,
        results: List[Dict],
        top_k: Optional[int] = None,
        combine_scores: bool = True,
        alpha: float = 0.7,
    ) -> List[RerankResult]:
        """
        Rerank search results using cross-encoder.

        Args:
            query: Search query
            results: List of result dicts with 'id', 'text', 'score' fields
            top_k: Return only top K results (None = all results)
            combine_scores: Whether to combine original and rerank scores
            alpha: Weight for rerank score (1-alpha for original score)

        Returns:
            List of reranked results sorted by final score (descending)
        """
        if not results:
            return []

        # Create query-document pairs
        pairs = self._create_pairs(query, results)

        # Score pairs with cross-encoder
        try:
            rerank_scores = self.model.predict(
                pairs, batch_size=self.batch_size, show_progress_bar=False
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Reranking failed: %s", e)
            # Fallback: return original results
            return [
                RerankResult(
                    doc_id=r.get("id", f"doc_{i}"),
                    text=r.get("text", ""),
                    original_score=r.get("score", 0.0),
                    rerank_score=0.0,
                    final_score=r.get("score", 0.0),
                    metadata=r.get("metadata"),
                )
                for i, r in enumerate(results)
            ]

        # Normalize rerank scores to 0-1 range
        rerank_scores = np.array(rerank_scores)
        if len(rerank_scores) > 0:
            min_score = rerank_scores.min()
            max_score = rerank_scores.max()

            if max_score > min_score:
                rerank_scores = (rerank_scores - min_score) / (max_score - min_score)
            else:
                rerank_scores = np.ones_like(rerank_scores)

        # Combine scores
        reranked_results = []

        for i, result in enumerate(results):
            original_score = result.get("score", 0.0)
            rerank_score = float(rerank_scores[i])

            # Combine scores (weighted average)
            if combine_scores:
                final_score = alpha * rerank_score + (1 - alpha) * original_score
            else:
                final_score = rerank_score

            reranked_results.append(
                RerankResult(
                    doc_id=result.get("id", f"doc_{i}"),
                    text=result.get("text", ""),
                    original_score=original_score,
                    rerank_score=rerank_score,
                    final_score=final_score,
                    metadata=result.get("metadata"),
                )
            )

        # Sort by final score (descending)
        reranked_results.sort(key=lambda x: x.final_score, reverse=True)

        # Return top K
        if top_k is not None:
            reranked_results = reranked_results[:top_k]

        return reranked_results

    def score_pair(self, query: str, document: str) -> float:
        """
        Score a single query-document pair.

        Args:
            query: Search query
            document: Document text

        Returns:
            Relevance score (higher = more relevant)
        """
        score = self.model.predict([(query, document)])[0]
        return float(score)

    def batch_rerank(
        self,
        queries: List[str],
        results_per_query: List[List[Dict]],
        top_k: Optional[int] = None,
        **kwargs,
    ) -> List[List[RerankResult]]:
        """
        Rerank results for multiple queries in batch.

        Args:
            queries: List of search queries
            results_per_query: List of result lists (one per query)
            top_k: Return only top K results per query
            **kwargs: Additional arguments for rerank()

        Returns:
            List of reranked result lists
        """
        if len(queries) != len(results_per_query):
            raise ValueError("Number of queries must match number of result lists")

        reranked_all = []

        for query, results in zip(queries, results_per_query):
            reranked = self.rerank(query, results, top_k=top_k, **kwargs)
            reranked_all.append(reranked)

        return reranked_all


class RerankerEnsemble:
    """
    Ensemble multiple rerankers for improved accuracy.

    Usage:
        ensemble = RerankerEnsemble([
            Reranker(model="cross-encoder/ms-marco-MiniLM-L-6-v2"),
            Reranker(model="cross-encoder/ms-marco-TinyBERT-L-6")
        ])

        results = ensemble.rerank(query, initial_results)
    """

    def __init__(self, rerankers: List[Reranker]):
        """
        Initialize reranker ensemble.

        Args:
            rerankers: List of Reranker instances
        """
        if not rerankers:
            raise ValueError("At least one reranker required")

        self.rerankers = rerankers

    def rerank(
        self,
        query: str,
        results: List[Dict],
        top_k: Optional[int] = None,
        voting_strategy: str = "average",
    ) -> List[RerankResult]:
        """
        Rerank using ensemble of models.

        Args:
            query: Search query
            results: List of result dicts
            top_k: Return only top K results
            voting_strategy: How to combine scores ('average', 'max', 'min')

        Returns:
            List of reranked results
        """
        # Get reranked results from each model
        all_reranked = []

        for reranker in self.rerankers:
            reranked = reranker.rerank(
                query,
                results,
                top_k=None,  # Don't filter yet
                combine_scores=False,  # Use rerank score only
            )
            all_reranked.append(reranked)

        # Combine scores
        combined_results = []

        for i, result in enumerate(results):
            doc_id = result.get("id", f"doc_{i}")

            # Get rerank scores from all models
            scores = [
                next(r.rerank_score for r in reranked if r.doc_id == doc_id)
                for reranked in all_reranked
            ]

            # Combine scores
            if voting_strategy == "average":
                final_score = np.mean(scores)
            elif voting_strategy == "max":
                final_score = np.max(scores)
            elif voting_strategy == "min":
                final_score = np.min(scores)
            else:
                raise ValueError(f"Unknown voting strategy: {voting_strategy}")

            combined_results.append(
                RerankResult(
                    doc_id=doc_id,
                    text=result.get("text", ""),
                    original_score=result.get("score", 0.0),
                    rerank_score=float(final_score),
                    final_score=float(final_score),
                    metadata=result.get("metadata"),
                )
            )

        # Sort by final score
        combined_results.sort(key=lambda x: x.final_score, reverse=True)

        # Return top K
        if top_k is not None:
            combined_results = combined_results[:top_k]

        return combined_results


# Example usage
def _demo() -> None:
    """Run a small demonstration of this module."""
    # Create reranker
    reranker = Reranker(model="cross-encoder/ms-marco-MiniLM-L-6-v2")

    # Sample search results
    query = "What is machine learning?"

    results = [
        {
            "id": "doc1",
            "text": "Machine learning is a subset of AI that enables computers to learn from data.",
            "score": 0.75,
        },
        {
            "id": "doc2",
            "text": "Deep learning uses neural networks with multiple layers.",
            "score": 0.68,
        },
        {
            "id": "doc3",
            "text": "Python is a popular programming language for data science.",
            "score": 0.62,
        },
        {
            "id": "doc4",
            "text": "Machine learning algorithms can be supervised or unsupervised.",
            "score": 0.58,
        },
    ]

    # Rerank results
    reranked = reranker.rerank(
        query=query, results=results, top_k=3, combine_scores=True, alpha=0.7
    )

    print(f"Reranked top 3 results for: '{query}'\n")
    for i, result in enumerate(reranked, 1):
        print(f"{i}. {result.doc_id}")
        print(f"   Original: {result.original_score:.3f}")
        print(f"   Rerank:   {result.rerank_score:.3f}")
        print(f"   Final:    {result.final_score:.3f}")
        print(f"   Text:     {result.text[:60]}...")
        print()


if __name__ == "__main__":
    _demo()
