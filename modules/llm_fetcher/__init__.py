"""LLM 请求模块的公共接口聚合。

本模块从 ``llm_fetcher`` 子模块统一导出核心类与异常，
方便外部以 ``from modules.llm_fetcher import LLMFetcher`` 的方式使用。

导出内容：
    - :class:`LLMFetcher`
    - :class:`LLMContext`
    - :class:`LLMBackendConfig`
    - :class:`LLMError`
    - :class:`LLMTimeoutError`
    - :class:`LLMBackendError`
"""

from .llm_fetcher import (
    LLMBackendConfig,
    LLMBackendError,
    LLMContext,
    LLMError,
    LLMFetcher,
    LLMTimeoutError,
)

__all__ = [
    "LLMFetcher",
    "LLMContext",
    "LLMBackendConfig",
    "LLMError",
    "LLMTimeoutError",
    "LLMBackendError",
]
