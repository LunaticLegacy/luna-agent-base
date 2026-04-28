from __future__ import annotations

import unittest
from pathlib import Path

from core.executor_parts.tool_scheduler import ToolScheduler
from core.results import ToolRequest
from core.toodefl import ToolContext
from tools.command_runner_tool import CommandRunnerTool


class Core:
    def __init__(self) -> None:
        self.tool = CommandRunnerTool()

    def get_tool(self, tool_name: str):
        if tool_name != "command_runner":
            raise KeyError(tool_name)
        return self.tool


class CommandRunnerToolTest(unittest.IsolatedAsyncioTestCase):
    async def test_command_runner_accepts_cmd_alias(self) -> None:
        scheduler = ToolScheduler(Core())
        result = await scheduler.execute_batch(
            [ToolRequest(id="cmd", tool="command_runner", args={"cmd": "printf hello"}, required=True)],
            context=ToolContext(
                workspace_root=Path.cwd(),
                capabilities={"command_execute"},
            ),
        )

        self.assertFalse(result.summary["failed_required"])
        self.assertEqual(result.results[0].status, "success")
        self.assertEqual(result.results[0].output["stdout"], "hello")

    async def test_command_runner_nonzero_exit_is_failed_result_with_stderr(self) -> None:
        scheduler = ToolScheduler(Core())
        result = await scheduler.execute_batch(
            [
                ToolRequest(
                    id="cmd",
                    tool="command_runner",
                    args={"command": "false"},
                    required=True,
                )
            ],
            context=ToolContext(
                workspace_root=Path.cwd(),
                capabilities={"command_execute"},
            ),
        )

        self.assertTrue(result.summary["failed_required"])
        self.assertEqual(result.results[0].status, "failed")
        self.assertEqual(result.results[0].error["returncode"], 1)

    async def test_command_runner_allows_safe_pwd_and_ls_compound_probe(self) -> None:
        scheduler = ToolScheduler(Core())
        result = await scheduler.execute_batch(
            [
                ToolRequest(
                    id="probe",
                    tool="command_runner",
                    args={"command": "pwd && ls -la"},
                    required=True,
                )
            ],
            context=ToolContext(
                workspace_root=Path.cwd(),
                capabilities={"command_execute"},
            ),
        )

        self.assertFalse(result.summary["failed_required"])
        self.assertEqual(result.results[0].status, "success")
        self.assertIn(str(Path.cwd()), result.results[0].output["stdout"])

    async def test_command_runner_denies_stderr_redirection_to_dev_null(self) -> None:
        scheduler = ToolScheduler(Core())
        result = await scheduler.execute_batch(
            [
                ToolRequest(
                    id="probe",
                    tool="command_runner",
                    args={
                        "command": (
                            "uname -m; "
                            "cat /proc/cpuinfo | head -5 2>/dev/null || echo \"no cpuinfo\""
                        )
                    },
                    required=True,
                )
            ],
            context=ToolContext(
                workspace_root=Path.cwd(),
                capabilities={"command_execute"},
            ),
        )

        self.assertTrue(result.summary["failed_required"])
        self.assertEqual(result.results[0].status, "failed")
        self.assertEqual(result.results[0].error["failure_kind"], "tool_policy_denied")
        self.assertEqual(result.results[0].error["reason"], "redirect_denied")

    async def test_command_runner_denies_toolchain_probe_with_compound_shell(self) -> None:
        scheduler = ToolScheduler(Core())
        result = await scheduler.execute_batch(
            [
                ToolRequest(
                    id="probe",
                    tool="command_runner",
                    args={
                        "command": (
                            "which g++ clang++ riscv64-linux-gnu-g++ qemu-riscv64 2>/dev/null; "
                            "echo \"---\"; "
                            "g++ --version 2>/dev/null | head -3; "
                            "echo \"---\"; "
                            "cmake --version 2>/dev/null | head -1"
                        )
                    },
                    required=True,
                )
            ],
            context=ToolContext(
                workspace_root=Path.cwd(),
                capabilities={"command_execute"},
            ),
        )

        self.assertTrue(result.summary["failed_required"])
        self.assertEqual(result.results[0].status, "failed")
        self.assertEqual(result.results[0].error["failure_kind"], "tool_policy_denied")


if __name__ == "__main__":
    unittest.main()
