import os
import sys
import logging
from typing import Any, Dict, Optional

from copotron.system_one.protocol import SystemOneProvider
from copotron.system_one.types import Question, SystemOneResponse
from copotron.system_one.cache import SystemOneCache, compute_cache_key
from copotron.system_one.providers.typesafe import TypeSafeProvider
from copotron.system_one.providers.fallback import HeuristicFallbackProvider
from copotron.system_one.providers.mock import MockProvider

logger = logging.getLogger("copotron.system_one")

class SystemOneClient:
    """
    Central Facade for System One Decision Operations.
    Coordinates provider resolution, SQLite persistent caching, and graceful offline fallback.
    """

    def __init__(
        self,
        provider: Optional[SystemOneProvider] = None,
        use_cache: bool = True,
        cache: Optional[SystemOneCache] = None,
    ):
        self._fallback_provider = HeuristicFallbackProvider()
        self._primary_provider = provider or self._resolve_provider()
        self._use_cache = use_cache
        self._cache = cache if cache is not None else SystemOneCache()

    def _resolve_provider(self) -> SystemOneProvider:
        env_pref = os.getenv("SYSTEM_ONE_PROVIDER", "").strip().lower()

        if env_pref == "mock":
            return MockProvider()
        elif env_pref == "fallback":
            return self._fallback_provider
        elif env_pref == "typesafe":
            return TypeSafeProvider()

        # Automatic detection: check if TypeSafe is available
        ts_provider = TypeSafeProvider()
        if ts_provider.is_available():
            return ts_provider

        return self._fallback_provider

    @property
    def provider(self) -> SystemOneProvider:
        return self._primary_provider

    def evaluate(
        self,
        state: Any,
        questions: Dict[str, Question],
        model: Optional[str] = None,
        skip_cache: bool = False,
    ) -> SystemOneResponse:
        """
        Evaluate questions against state with caching and automatic fallback.
        """
        target_model = model or os.getenv("SYSTEM_ONE_MODEL") or "jev-latest"
        provider_name = self._primary_provider.provider_name

        cache_key = None
        if self._use_cache and not skip_cache:
            try:
                cache_key = compute_cache_key(provider_name, target_model, state, questions)
                cached_resp = self._cache.get(cache_key)
                if cached_resp is not None:
                    return cached_resp
            except Exception as e:
                logger.debug(f"Cache lookup failed: {e}")

        # Attempt evaluation via primary provider
        try:
            resp = self._primary_provider.evaluate(state=state, questions=questions, model=target_model)
        except Exception as e:
            # If primary provider fails (e.g. network disconnect, auth failure), fall back
            if provider_name != self._fallback_provider.provider_name:
                print(f"Warning: System One provider '{provider_name}' failed ({e}). Falling back to local heuristics.", file=sys.stderr)
                resp = self._fallback_provider.evaluate(state=state, questions=questions, model="fallback")
            else:
                raise

        # Save to cache if enabled
        if self._use_cache and cache_key:
            try:
                self._cache.set(cache_key, resp)
            except Exception as e:
                logger.debug(f"Cache set failed: {e}")

        return resp


_GLOBAL_CLIENT: Optional[SystemOneClient] = None

def get_system_one_client() -> SystemOneClient:
    """Retrieve or initialize the global singleton SystemOneClient."""
    global _GLOBAL_CLIENT
    if _GLOBAL_CLIENT is None:
        _GLOBAL_CLIENT = SystemOneClient()
    return _GLOBAL_CLIENT
