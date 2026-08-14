"""Merchant Embedding Service for Semantic Spoofing Detection.

Uses sentence-transformers to create embeddings of merchant names and detect
semantic similarity. This catches spoofed merchants like "AMAZ0N_STORE" that
are similar to legitimate "AMAZON".
"""

import logging
from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer, util

logger = logging.getLogger(__name__)


class MerchantEmbeddingService:
    """Detects merchant name spoofing using semantic embeddings.
    
    Compares merchant names using sentence embeddings and cosine similarity
    to detect fraudsters who use similar-sounding names.
    """

    # Known legitimate merchants (would be expanded in production)
    TRUSTED_MERCHANTS = {
        "amazon": "Amazon",
        "ebay": "eBay",
        "paypal": "PayPal",
        "stripe": "Stripe",
        "apple": "Apple",
        "google": "Google",
        "microsoft": "Microsoft",
        "netflix": "Netflix",
        "spotify": "Spotify",
        "walmart": "Walmart",
    }

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """Initialize embedding service with a pre-trained model.
        
        Args:
            model_name: HuggingFace model identifier (default: lightweight all-MiniLM-L6-v2)
        """
        try:
            self.model = SentenceTransformer(model_name)
            self.model_name = model_name
            logger.info("MerchantEmbeddingService initialized with model: %s", model_name)
        except Exception as exc:
            logger.error("Failed to load embedding model: %s", exc)
            self.model = None

    def is_available(self) -> bool:
        """Check if model is loaded and ready."""
        return self.model is not None

    def get_embedding(self, merchant_name: str) -> Optional[np.ndarray]:
        """Get embedding vector for a merchant name.
        
        Args:
            merchant_name: Name of the merchant
            
        Returns:
            Embedding vector (384-dim for all-MiniLM-L6-v2) or None if failed
        """
        if not self.is_available():
            return None

        try:
            embedding = self.model.encode(merchant_name.lower(), convert_to_numpy=True)
            return embedding
        except Exception as exc:
            logger.error("Failed to embed merchant name '%s': %s", merchant_name, exc)
            return None

    def detect_spoofing(
        self,
        merchant_name: str,
        similarity_threshold: float = 0.85,
    ) -> tuple[bool, Optional[str], Optional[float]]:
        """Detect if merchant name is spoofing a trusted merchant.
        
        Args:
            merchant_name: Name to check
            similarity_threshold: Cosine similarity threshold (0-1). Default 0.85 = high similarity
            
        Returns:
            Tuple of (is_spoofed, matched_trusted_merchant, similarity_score)
            - is_spoofed: True if detected as spoofing
            - matched_trusted_merchant: Name of the trusted merchant it's spoofing
            - similarity_score: Cosine similarity value (0-1)
        """
        if not self.is_available():
            return False, None, None

        try:
            merchant_lower = merchant_name.lower()
            merchant_embedding = self.get_embedding(merchant_name)

            if merchant_embedding is None:
                return False, None, None

            # Check against all trusted merchants
            max_similarity = 0.0
            best_match = None

            for trusted_key, trusted_name in self.TRUSTED_MERCHANTS.items():
                trusted_embedding = self.get_embedding(trusted_key)
                if trusted_embedding is None:
                    continue

                # Compute cosine similarity
                similarity = util.pytorch_cos_sim(merchant_embedding, trusted_embedding)[0][0].item()

                if similarity > max_similarity:
                    max_similarity = similarity
                    best_match = trusted_name

            # Determine if spoofed
            is_spoofed = max_similarity >= similarity_threshold

            if is_spoofed:
                logger.warning(
                    "Merchant spoofing detected: '%s' (similarity: %.3f) matches '%s'",
                    merchant_name,
                    max_similarity,
                    best_match,
                )
            else:
                logger.debug(
                    "Merchant '%s' passed spoofing check (best match: %.3f to %s)",
                    merchant_name,
                    max_similarity,
                    best_match,
                )

            return is_spoofed, best_match, float(max_similarity)

        except Exception as exc:
            logger.error("Error during spoofing detection for '%s': %s", merchant_name, exc)
            return False, None, None

    def add_trusted_merchant(self, merchant_key: str, merchant_name: str) -> None:
        """Add a new trusted merchant to the comparison set.
        
        Args:
            merchant_key: Lowercase key (e.g., "amazon")
            merchant_name: Display name (e.g., "Amazon")
        """
        self.TRUSTED_MERCHANTS[merchant_key.lower()] = merchant_name
        logger.info("Added trusted merchant: %s -> %s", merchant_key, merchant_name)
