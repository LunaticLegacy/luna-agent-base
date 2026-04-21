# Example Frontend Receive Payloads

This document shows sample payloads that the frontend can receive and explains what they mean.

## 1. Example Swarm Result

```json
{
  "metadata": {},
  "output": {
    "bytes": 34,
    "context": {
      "agent_id": null,
      "node_id": 7,
      "rounds": 4
    },
    "path": "outputs/deepseek_demo_final.txt",
    "written": true
  },
  "rounds": 4,
  "success": true,
  "swarm": "deepseek_demo",
  "trace": []
}
```

### Meaning

- `swarm`: the executed swarm name
- `success`: whether the run succeeded
- `rounds`: the final round counter
- `output`: the final payload returned by the graph
- `trace`: execution trace
- `metadata`: run-time metadata

## 2. Trace Payload Notes

Each trace item typically contains:

- `node_id`
- `node_name`
- `node_type`
- `input_payload`
- `output_payload`
- `status`
- `error`
- `branch`

The frontend should use:

- `output_payload` for human-readable content
- `trace` for debugging and runtime inspection
- `metadata` for semantic hints and graph state

## 3. Important Caveat

Some payloads can still contain raw model objects if they are not normalized. Production-facing responses should always convert them into JSON-safe structures first.

