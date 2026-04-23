from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from modules.llm_fetcher import LLMBackendConfig, LLMFetcher, LLMTimeoutError


class LLMFetcherTimeoutRetryTest(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_retries_once_on_timeout_then_succeeds(self) -> None:
        fetcher = LLMFetcher(
            backends=[
                LLMBackendConfig(
                    name="primary",
                    provider="litellm",
                    model="moonshot/kimi-k2.5",
                    api_key="test-key",
                    timeout=1.0,
                    max_retries=0,
                )
            ]
        )

        calls = {"count": 0}

        def fake_create_completion(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise TimeoutError("Request timed out.")
            return {"ok": True, "attempt": calls["count"]}

        fetcher._create_completion = fake_create_completion  # type: ignore[method-assign]

        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        with patch("modules.llm_fetcher.llm_fetcher.asyncio.to_thread", new=fake_to_thread):
            result = await fetcher.fetch(msg="hello")
        self.assertEqual(result, {"ok": True, "attempt": 2})
        self.assertEqual(calls["count"], 2)

    async def test_timeout_exception_is_normalized(self) -> None:
        fetcher = LLMFetcher(
            backends=[
                LLMBackendConfig(
                    name="primary",
                    provider="litellm",
                    model="moonshot/kimi-k2.5",
                    api_key="test-key",
                )
            ]
        )
        normalized = fetcher._normalize_exception(
            fetcher.backends["primary"],
            TimeoutError("Request timed out."),
        )
        self.assertIsInstance(normalized, LLMTimeoutError)


if __name__ == "__main__":
    unittest.main()
