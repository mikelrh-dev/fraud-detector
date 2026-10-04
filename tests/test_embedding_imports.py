"""Import contract for the embedding stack.

The embedding worker crashed in production while the suite stayed green. The
pinned ``sentence-transformers`` release imports ``cached_download`` from
``huggingface_hub``, an API removed before the hub version this stack resolves
to, so ``src.services.merchant_embedding_service`` raised ImportError at import
time. ``tests/workers/conftest.py`` papers over exactly that by installing a
``MagicMock`` in ``sys.modules`` when the real package fails to import, so every
worker test kept collecting and passing against a stand-in for a dependency that
was dead in the container.

This module asserts the contract at the service boundary, where that shim does
not apply, so a broken dependency turns the suite red instead of the container.

The third-party imports are deliberately deferred into the test bodies. A
module-level import of a broken dependency aborts collection with a single
error and reports nothing about the rest of the contract; importing per test
keeps this file collectible and turns each clause into its own named failure.

Everything here is offline by design: the module asserts importability and the
shape of the APIs ``MerchantEmbeddingService`` calls. No model weights are
downloaded, so this file stays runnable in CI with an empty HF cache.
"""

import sys
import types
from importlib import import_module

SERVICE_MODULE = "src.services.merchant_embedding_service"


def _approx(actual: float, expected: float, tol: float = 1e-5) -> bool:
    """Tolerant float comparison."""
    return abs(actual - expected) <= tol


def test_service_module_imports() -> None:
    """The module the embedding worker imports at startup must import cleanly."""
    module = import_module(SERVICE_MODULE)
    assert module is not None


def test_sentence_transformers_imports() -> None:
    """The pinned package itself must import, without a stand-in."""
    module = import_module("sentence_transformers")
    assert module is not None


def test_sentence_transformers_is_not_swapped_for_a_mock() -> None:
    """The real package must be loaded, not a test stand-in.

    A ``sys.modules`` entry installed by a conftest shim is a MagicMock instance,
    not a ``types.ModuleType``. Asserting the type keeps this test honest even
    when the whole suite is collected in one run and another conftest has
    already mutated ``sys.modules``.
    """
    module = import_module("sentence_transformers")
    assert isinstance(module, types.ModuleType), (
        "sentence_transformers resolved to a "
        f"{type(module).__name__}, not a real module: a shim is substituting a "
        "stand-in for the real package."
    )


def test_sentence_transformer_class_is_available() -> None:
    """``MerchantEmbeddingService`` instantiates ``SentenceTransformer`` directly."""
    from sentence_transformers import SentenceTransformer

    assert isinstance(SentenceTransformer, type), (
        f"SentenceTransformer must be a class, got {type(SentenceTransformer).__name__}."
    )


def test_service_uses_the_real_sentence_transformer() -> None:
    """The service must bind the real class, not a stand-in injected at import."""
    from sentence_transformers import SentenceTransformer

    service = import_module(SERVICE_MODULE)
    assert service.SentenceTransformer is SentenceTransformer


def test_cosine_similarity_util_is_available() -> None:
    """``detect_spoofing`` scores candidates through ``util.pytorch_cos_sim``."""
    from sentence_transformers import util

    assert hasattr(util, "pytorch_cos_sim")
    assert callable(util.pytorch_cos_sim)


def test_pytorch_cos_sim_orders_identical_and_orthogonal_vectors() -> None:
    """Prove the exact similarity call the spoofing detector makes.

    ``detect_spoofing`` computes ``util.pytorch_cos_sim(a, b)[0][0].item()`` and
    compares the result against a 0.85 threshold, so this asserts the real return
    shape plus the three anchor values that threshold depends on. Vectors are
    built by hand, so this stays offline.
    """
    import torch
    from sentence_transformers import util

    identical = util.pytorch_cos_sim(torch.tensor([[1.0, 2.0, 3.0]]), torch.tensor([[1.0, 2.0, 3.0]]))
    orthogonal = util.pytorch_cos_sim(torch.tensor([[1.0, 0.0, 0.0]]), torch.tensor([[0.0, 1.0, 0.0]]))
    opposite = util.pytorch_cos_sim(torch.tensor([[1.0, 0.0, 0.0]]), torch.tensor([[-1.0, 0.0, 0.0]]))

    assert _approx(identical[0][0].item(), 1.0), f"identical vectors gave {identical[0][0].item()}"
    assert _approx(orthogonal[0][0].item(), 0.0), f"orthogonal vectors gave {orthogonal[0][0].item()}"
    assert _approx(opposite[0][0].item(), -1.0), f"opposite vectors gave {opposite[0][0].item()}"


def test_service_module_is_registered_in_sys_modules() -> None:
    """Guard the key the worker resolves the service through.

    Independent of the ``from ... import`` aliases used elsewhere in this file:
    the worker does ``from src.services.merchant_embedding_service import
    MerchantEmbeddingService``, so that exact key must be the real module.
    """
    import_module(SERVICE_MODULE)
    module = sys.modules[SERVICE_MODULE]
    assert isinstance(module, types.ModuleType), (
        f"{SERVICE_MODULE} resolved to a {type(module).__name__}, not a real module."
    )
    assert hasattr(module, "MerchantEmbeddingService")
