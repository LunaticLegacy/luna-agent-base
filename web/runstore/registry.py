"""后台运行注册表。

RunRegistry 以线程安全的方式管理所有后台图运行（RunRecord），
提供启动、查询、停止与事件流式输出的能力。
"""
from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.executor import GraphExecutor
from core.results import ExecutionEvent

from .record import RunRecord


@dataclass
class RunRegistry:
    """线程安全的运行注册表。

    Attributes:
        _runs: 以 run_id 为键的运行记录字典。
        _run_cores: 以 run_id 为键的关联 core 字典，用于请求停止。
        _lock: 保护 _runs 与 _run_cores 的 RLock。
    """

    def __init__(self) -> None:
        self._runs: Dict[str, RunRecord] = {}
        self._run_cores: Dict[str, Any] = {}
        self._lock = threading.RLock()

    def launch_run(
        self,
        *,
        swarm_name: str,
        core,
        graph,
        initial_payload: Any,
        rounds: int = 0,
        meta_mode: bool = False,
    ) -> RunRecord:
        """创建运行记录并在守护线程中启动图执行。

        Args:
            swarm_name: 所属 swarm 名称。
            core: swarm 核心实例。
            graph: 要执行的图对象。
            initial_payload: 初始输入负载。
            rounds: 最大执行轮数。
            meta_mode: 是否使用 MetaExecutor（元执行器）。

        Returns:
            已启动的运行记录。
        """
        run_id = uuid.uuid4().hex
        record = RunRecord(run_id=run_id, swarm_name=swarm_name, rounds=rounds)
        runtime_info_dir = getattr(core, "get_runtime_info_dir", None)
        if callable(runtime_info_dir):
            storage_root = runtime_info_dir()
            if storage_root is not None:
                # 为运行分配独立的持久化目录，用于保存 events.jsonl 与快照
                record.bind_storage_dir(Path(storage_root) / "runs" / run_id)
        with self._lock:
            self._runs[run_id] = record
            self._run_cores[run_id] = core

        thread = threading.Thread(
            target=self._worker,
            kwargs={
                "record": record,
                "swarm_name": swarm_name,
                "core": core,
                "graph": graph,
                "initial_payload": initial_payload,
                "rounds": rounds,
                "meta_mode": meta_mode,
            },
            daemon=True,
            name=f"angelus-run-{run_id[:8]}",
        )
        thread.start()
        return record

    def get_run(self, run_id: str) -> Optional[RunRecord]:
        """根据 ID 获取运行记录。

        Args:
            run_id: 运行唯一标识。

        Returns:
            RunRecord 实例，或 None。
        """
        with self._lock:
            return self._runs.get(run_id)

    def list_runs(self, swarm_name: Optional[str] = None) -> List[RunRecord]:
        """列出运行记录，可按 swarm 过滤。

        Args:
            swarm_name: 可选的 swarm 名称过滤器。

        Returns:
            运行记录列表，保持插入顺序。
        """
        with self._lock:
            runs = list(self._runs.values())
        if swarm_name is None:
            return runs
        return [record for record in runs if record.swarm_name == swarm_name]

    def snapshot(self, run_id: str) -> Optional[Dict[str, Any]]:
        """获取单条运行的 JSON 快照。

        Args:
            run_id: 运行唯一标识。

        Returns:
            快照字典，或 None（运行不存在）。
        """
        record = self.get_run(run_id)
        if record is None:
            return None
        return record.snapshot()

    def active_run_count(self, swarm_name: Optional[str] = None) -> int:
        """统计活跃运行数。

        Args:
            swarm_name: 可选的 swarm 名称过滤器。

        Returns:
            未完成的运行数量。
        """
        with self._lock:
            return sum(
                1
                for record in self._runs.values()
                if not record._done and (swarm_name is None or record.swarm_name == swarm_name)
            )

    def active_run_ids(self, swarm_name: Optional[str] = None) -> List[str]:
        """获取活跃运行的 ID 列表。

        Args:
            swarm_name: 可选的 swarm 名称过滤器。

        Returns:
            活跃运行 ID 列表。
        """
        with self._lock:
            return [
                record.run_id
                for record in self._runs.values()
                if not record._done and (swarm_name is None or record.swarm_name == swarm_name)
            ]

    def stop_run(self, run_id: str, stop_type: str = "soft") -> Optional[RunRecord]:
        """请求停止一条活跃运行。

        会同时调用 core 的 request_stop，向执行引擎发送停止信号。

        Args:
            run_id: 运行唯一标识。
            stop_type: "soft" 或 "hard"。

        Returns:
            被停止的运行记录，或 None（运行不存在或已结束）。
        """
        record = self.get_run(run_id)
        if record is None:
            return None
        if record._done:
            return None
        record.stop(stop_type)
        core = self._run_cores.get(run_id)
        if core is not None:
            request_stop = getattr(core, "request_stop", None)
            if callable(request_stop):
                request_stop(run_id, stop_type)
        return record

    def _worker(
        self,
        *,
        record: RunRecord,
        swarm_name: str,
        core,
        graph,
        initial_payload: Any,
        rounds: int,
        meta_mode: bool = False,
    ) -> None:
        """后台线程的异步执行入口。

        根据 meta_mode 选择 MetaExecutor 或 GraphExecutor，
        并在异常时自动注入 run.failed 事件。
        """
        async def _execute() -> None:
            if meta_mode:
                from core.meta_executor import MetaExecutor

                meta = MetaExecutor(max_iterations=5)
                await meta.run(
                    graph,
                    core,
                    initial_payload,
                    rounds=rounds,
                    run_id=record.run_id,
                    swarm_name=swarm_name,
                    event_sink=record.append_event,
                )
            else:
                await GraphExecutor().execute(
                    graph,
                    core,
                    initial_payload,
                    rounds=rounds,
                    run_id=record.run_id,
                    swarm_name=swarm_name,
                    event_sink=record.append_event,
                )

        try:
            asyncio.run(_execute())
        except Exception as exc:
            # 若执行过程中抛出未捕获异常，且记录尚未标记完成，
            # 则自动追加 run.failed 事件，保证前端能收到终止通知
            if not record._done:
                record.append_event(
                    ExecutionEvent(
                        run_id=record.run_id,
                        swarm_name=swarm_name,
                        event_type="run.failed",
                        rounds=record.rounds,
                        status="failed",
                        data={
                            "error": str(exc),
                            "state_snapshot": record.current_state,
                        },
                    )
                )
        finally:
            with self._lock:
                self._run_cores.pop(record.run_id, None)
