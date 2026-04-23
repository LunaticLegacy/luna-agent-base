from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.runtime_info import RuntimeInfoManager


class RuntimeInfoTest(unittest.TestCase):
    def test_runtime_info_redacts_secrets_and_truncates_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = RuntimeInfoManager(Path(tmp_dir), agent_name="demo")
            event = manager.record(
                action="spawn",
                subject_kind="agent",
                subject_id="researcher",
                detail={
                    "api_key": "sk-secret",
                    "spawned_agent_prompt": "x" * 700,
                    "nested": {"token": "secret-token"},
                },
            )

            detail = event["detail"]
            self.assertEqual(detail["api_key"], "[redacted]")
            self.assertEqual(detail["nested"]["token"], "[redacted]")
            self.assertIn("[truncated]", detail["spawned_agent_prompt"])


if __name__ == "__main__":
    unittest.main()
