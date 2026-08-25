"""Shared fixtures/shims for worker tests.

The pinned ``sentence_transformers`` release in this environment fails to import
(stale ``huggingface_hub.cached_download`` API), which would break collection of
any module importing :mod:`src.workers.embedding_worker`. Every embedding-worker
test stubs ``MerchantEmbeddingService`` anyway, so when the real package cannot
be imported we substitute a minimal stand-in before the worker module is loaded.
If the package imports cleanly, it is left untouched.
"""

import sys
from unittest.mock import MagicMock

try:
    import sentence_transformers  # noqa: F401
except Exception:
    sys.modules["sentence_transformers"] = MagicMock()
