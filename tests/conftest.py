from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SRC_PKG = ROOT / "src" / "contextgo"
SCRIPTS = ROOT / "scripts"

for path in (str(SRC), str(SRC_PKG), str(SCRIPTS)):
    if path not in sys.path:
        sys.path.insert(0, path)


@pytest.fixture(autouse=True)
def _clear_module_caches():
    """Clear module-level caches between tests."""
    yield
    # session_index caches
    try:
        from contextgo import session_index

        if hasattr(session_index, "_SEARCH_RESULT_CACHE"):
            session_index._SEARCH_RESULT_CACHE.clear()
    except ImportError:
        try:
            import session_index  # type: ignore[import]

            if hasattr(session_index, "_SEARCH_RESULT_CACHE"):
                session_index._SEARCH_RESULT_CACHE.clear()
        except ImportError:
            pass
    # vector_index caches
    try:
        from contextgo import vector_index

        if hasattr(vector_index, "_VECTOR_MATRIX_CACHE"):
            vector_index._VECTOR_MATRIX_CACHE.clear()
    except ImportError:
        try:
            import vector_index  # type: ignore[import]

            if hasattr(vector_index, "_VECTOR_MATRIX_CACHE"):
                vector_index._VECTOR_MATRIX_CACHE.clear()
        except ImportError:
            pass
