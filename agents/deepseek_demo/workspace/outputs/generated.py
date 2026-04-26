```python
import abc
from typing import Any, Optional, Tuple

class Action(abc.ABC):
    """抽象动作：执行一步操作并更新状态"""
    @abc.abstractmethod
    def execute(self, state: Any) -> Any:
        """接收当前状态，返回新状态"""
        pass

class Checker(abc.ABC):
    """抽象检查器：判断是否达到目标"""
    @abc.abstractmethod
    def is_done(self, state: Any) -> bool:
        """返回True表示目标已达成，应终止循环"""
        pass

class Agent:
    """基础Agent，执行-检查循环，直到目标达成"""
    def __init__(self, action: Action, checker: Checker, initial_state: Any = None):
        self.action = action
        self.checker = checker
        self.state = initial_state

    def run(self, max_steps: int = 1000) -> Tuple[Any, int]:
        """运行循环，返回(最终状态, 执行步数)"""
        steps = 0
        while not self.checker.is_done(self.state):
            if steps >= max_steps:
                raise RuntimeError(f"达到最大步数 {max_steps}，循环未终止")
            self.state = self.action.execute(self.state)
            steps += 1
        return self.state, steps

# ---------------------------
# 示例：累加数字直到总和超过阈值
# ---------------------------

class SumAction(Action):
    """向当前总和追加一个固定数值"""
    def __init__(self, increment: float = 1.0):
        self.increment = increment

    def execute(self, state: Any) -> Any:
        """state应为数值类型（int/float）"""
        return state + self.increment

class SumThresholdChecker(Checker):
    """检查总和是否超过阈值"""
    def __init__(self, threshold: float):
        self.threshold = threshold

    def is_done(self, state: Any) -> bool:
        return state > self.threshold

if __name__ == "__main__":
    # 设定阈值 10，步长 0.5，期望循环 (10/0.5) + 1 = 21 步后超出阈值
    threshold = 10.0
    increment = 0.5
    action = SumAction(increment=increment)
    checker = SumThresholdChecker(threshold=threshold)
    initial_state = 0.0

    agent = Agent(action=action, checker=checker, initial_state=initial_state)
    final_state, steps = agent.run()

    print(f"初始总和: {initial_state}")
    print(f"步长: {increment}")
    print(f"阈值: {threshold}")
    print(f"最终总和: {final_state:.2f}")
    print(f"执行步数: {steps}")
    assert final_state > threshold, "Demo失败：未达到目标"
    print("Demo成功：循环正确终止。")
```