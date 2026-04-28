from __future__ import annotations

import unittest
from types import SimpleNamespace

from core.errors import OutputParseError
from core.executor_parts.engine import GraphExecutor
from core.policy import AgentNode
from core.results import ExecutionState


class OutputCodecTest(unittest.TestCase):
    def test_json_optional_malformed_json_falls_back_to_raw_text(self) -> None:
        node = AgentNode(node_id=1, node_name="planner", blueprint_ref="a", metadata={"output_mode": "json_optional"})
        result = GraphExecutor()._normalize_agent_node_result(
            ExecutionState(payload="input"),
            node,
            SimpleNamespace(assistant_message='{"bad": '),
            input_payload="input",
        )

        self.assertEqual(result.output_payload, '{"bad": ')

    def test_json_required_malformed_json_raises_parse_error_with_location(self) -> None:
        node = AgentNode(node_id=1, node_name="planner", blueprint_ref="a", metadata={"output_mode": "json_required"})

        with self.assertRaises(OutputParseError) as caught:
            GraphExecutor()._normalize_agent_node_result(
                ExecutionState(payload="input"),
                node,
                SimpleNamespace(assistant_message='{\n  "bad": \n}'),
                input_payload="input",
            )

        self.assertEqual(caught.exception.parser_stage, "agent_structured_output")
        self.assertIsNotNone(caught.exception.line)
        self.assertIsNotNone(caught.exception.column)
        self.assertIn('"bad"', caught.exception.raw_output_near_error)

    def test_raw_text_cpp_code_block_is_not_parsed(self) -> None:
        text = "```cpp\nint main() { return 0; }\n```"
        node = AgentNode(node_id=1, node_name="coder", blueprint_ref="a", metadata={"output_mode": "raw_text"})
        result = GraphExecutor()._normalize_agent_node_result(
            ExecutionState(payload="input"),
            node,
            SimpleNamespace(assistant_message=text),
            input_payload="input",
        )

        self.assertEqual(result.output_payload, text)


if __name__ == "__main__":
    unittest.main()
