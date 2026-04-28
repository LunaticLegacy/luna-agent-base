"""单条运行记录的数据类，维护后台图运行的全生命周期状态。

RunRecord 在内存中保存运行的事件序列、当前节点、状态机与错误信息，
并通过 threading.Condition 支持多线程安全的事件追加与流式读取。
同时可选择绑定持久化目录，将事件与快照落盘为 JSONL / JSON 文件。
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from core.results import ExecutionEvent
from web.utils import to_jsonable

from .serialization import _event_name, _utc_now_iso


@dataclass
class RunRecord:
    """后台图运行的内存状态容器。

    Attributes:
        run_id: 运行唯一标识（UUID hex）。
        swarm_name: 所属 swarm 名称。
        storage_dir: 可选的持久化根目录。
        status: 运行状态机（queued / running / completed / failed / stopped / stopping_*）。
        created_at: 创建时间 ISO 字符串。
        started_at: 实际开始时间。
        finished_at: 结束时间。
        rounds: 已执行轮数。
        current_node_id: 当前正在执行的节点 ID。
        current_node_name: 当前节点名称。
        current_node_type: 当前节点类型。
        current_state: 最近一次状态快照。
        final_state: 最终完成时的状态快照。
        error: 错误信息（若有）。
        events: 事件列表，每个元素为字典。
        _done: 是否已结束（completed / failed / stopped）。
        _stop_type: 被请求的停止类型（soft / hard）。
        _condition: 线程条件变量，用于 stream_events 的阻塞等待。
    """

    run_id: str
    swarm_name: str
    storage_dir: Optional[Path] = None
    status: str = "queued"
    created_at: str = field(default_factory=_utc_now_iso)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    rounds: int = 0
    current_node_id: Optional[int] = None
    current_node_name: Optional[str] = None
    current_node_type: Optional[str] = None
    current_state: Dict[str, Any] = field(default_factory=dict)
    final_state: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    events: list[Dict[str, Any]] = field(default_factory=list)
    _done: bool = False
    _stop_type: Optional[str] = None
    _condition: threading.Condition = field(default_factory=threading.Condition, repr=False, compare=False)

    def __post_init__(self) -> None:
        """若构造时传入 storage_dir，立即绑定并创建目录。"""
        if self.storage_dir is not None:
            self.bind_storage_dir(self.storage_dir)

    @property
    def events_path(self) -> Optional[Path]:
        """事件持久化文件路径（JSONL）。"""
        if self.storage_dir is None:
            return None
        return self.storage_dir / "events.jsonl"

    @property
    def snapshot_path(self) -> Optional[Path]:
        """快照持久化文件路径（JSON）。"""
        if self.storage_dir is None:
            return None
        return self.storage_dir / "current.json"

    def bind_storage_dir(self, storage_dir: Path) -> None:
        """绑定持久化目录并确保其存在。

        Args:
            storage_dir: 目标目录路径。
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def append_event(self, event: ExecutionEvent | Dict[str, Any]) -> Dict[str, Any]:
        """追加一条事件并更新状态机与持久化文件。

        操作在 Condition 保护下进行，并通知所有等待中的流式读取线程。

        Args:
            event: 原始事件对象或已转换的字典。

        Returns:
            标准化后的事件字典。
        """
        payload = to_jsonable(event)
        with self._condition:
            self.events.append(payload)
            self._apply_event(payload)
            self._persist_locked(payload)
            self._condition.notify_all()
        return payload

    def _apply_event(self, event: Dict[str, Any]) -> None:
        """根据事件类型更新运行状态机。

        处理逻辑覆盖 run 级别事件（started / completed / stopped / failed）
        与 node 级别事件，同时维护 current_node_id、current_state、error 等字段。
        """
        event_type = str(event.get("event_type") or "").strip()
        timestamp = event.get("timestamp")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}

        # 更新轮数（若事件携带该字段）
        if event.get("rounds") is not None:
            try:
                self.rounds = int(event["rounds"])
            except Exception:
                pass

        # run 级别状态转换
        if event_type == "run.started":
            self.status = "running"
            self.started_at = self.started_at or _utc_now_iso()
            if data.get("state_snapshot") is not None:
                self.current_state = to_jsonable(data["state_snapshot"])
        elif event_type == "run.completed":
            self.status = "completed"
            self.finished_at = self.finished_at or _utc_now_iso()
            if data.get("state_snapshot") is not None:
                self.final_state = to_jsonable(data["state_snapshot"])
                self.current_state = dict(self.final_state)
            self._done = True
        elif event_type == "run.stopped":
            self.status = "stopped"
            self.finished_at = self.finished_at or _utc_now_iso()
            if data.get("state_snapshot") is not None:
                self.final_state = to_jsonable(data["state_snapshot"])
                self.current_state = dict(self.final_state)
            self._done = True
        elif event_type == "run.failed":
            self.status = "failed"
            self.finished_at = self.finished_at or _utc_now_iso()
            self.error = str(data.get("error") or event.get("error") or "run failed")
            if data.get("state_snapshot") is not None:
                self.current_state = to_jsonable(data["state_snapshot"])
            self._done = True
        else:
            # node 级别事件：更新当前节点上下文
            node_id = event.get("node_id")
            if node_id is not None:
                try:
                    self.current_node_id = int(node_id)
                except Exception:
                    self.current_node_id = None
            self.current_node_name = event.get("node_name") or self.current_node_name
            self.current_node_type = event.get("node_type") or self.current_node_type
            if data.get("state_snapshot") is not None:
                self.current_state = to_jsonable(data["state_snapshot"])
            if event_type == "node.failed":
                self.error = str(data.get("error") or event.get("error") or "node failed")

        # 若尚未记录 started_at，且收到 run/node started 事件，则补录当前时间
        if timestamp is not None and self.started_at is None and event_type in {"run.started", "node.started"}:
            self.started_at = _utc_now_iso()

    def stop(self, stop_type: str) -> bool:
        """请求停止本次运行。

        实际停止由执行引擎检查 core 的 stop 事件完成；本方法仅记录意图
        并更新状态，以便前端通过 snapshot 观察到 stopping_* 状态。

        Args:
            stop_type: "soft" 或 "hard"。

        Returns:
            True 表示成功记录停止请求；False 表示运行已结束。
        """
        with self._condition:
            if self._done:
                return False
            self._stop_type = stop_type
            if stop_type == "hard":
                self.status = "stopping_hard"
            else:
                self.status = "stopping_soft"
            return True

    def snapshot(self) -> Dict[str, Any]:
        """生成当前运行的 JSON 安全快照。

        Returns:
            包含运行元数据、状态、事件数与相关 URL 的字典。
        """
        with self._condition:
            events_url = f"/api/runs/{self.run_id}/events"
            status_url = f"/api/runs/{self.run_id}"
            return {
                "success": self.status == "completed",
                "run_id": self.run_id,
                "swarm": self.swarm_name,
                "status": self.status,
                "created_at": self.created_at,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "rounds": self.rounds,
                "current_node_id": self.current_node_id,
                "current_node_name": self.current_node_name,
                "current_node_type": self.current_node_type,
                "state": to_jsonable(self.current_state),
                "final_state": to_jsonable(self.final_state),
                "error": self.error,
                "event_count": len(self.events),
                "events_url": events_url,
                "status_url": status_url,
            }

    def stream_events(self, *, after: int = 0, heartbeat_seconds: float = 15.0) -> Iterator[str]:
        """以 SSE 帧形式流式输出事件。

        当事件不足时，通过 Condition.wait 阻塞等待新事件或超时，
        超时后发送 keepalive 注释行以维持连接。

        Args:
            after: 起始索引（不含）。
            heartbeat_seconds: 心跳/超时秒数。

        Yields:
            SSE 格式的字符串帧。
        """
        index = max(after, 0)
        while True:
            frames: list[str] = []
            needs_keepalive = False
            with self._condition:
                # 若当前索引已追上事件末尾且运行未结束，则阻塞等待
                while index >= len(self.events) and not self._done:
                    self._condition.wait(timeout=heartbeat_seconds)
                    if index >= len(self.events) and not self._done:
                        needs_keepalive = True
                        break
                while index < len(self.events):
                    event = self.events[index]
                    index += 1
                    frames.append(f"event: {_event_name(event)}\n")
                    frames.append(f"data: {json.dumps(to_jsonable(event), ensure_ascii=False)}\n\n")
                done = self._done and index >= len(self.events)
            if needs_keepalive:
                yield ": keepalive\n\n"
                continue
            for frame in frames:
                yield frame
            if done:
                break

    def _persist_locked(self, event: Dict[str, Any]) -> None:
        """在已持有锁的情况下将事件与快照持久化到磁盘。

        使用写临时文件后 replace 的策略，避免写入过程中断导致文件损坏。

        Args:
            event: 刚追加的事件字典。
        """
        if self.storage_dir is None:
            return
        events_path = self.events_path
        snapshot_path = self.snapshot_path
        if events_path is None or snapshot_path is None:
            return
        events_path.parent.mkdir(parents=True, exist_ok=True)
        with events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
        tmp_path = snapshot_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(self.snapshot(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(snapshot_path)
