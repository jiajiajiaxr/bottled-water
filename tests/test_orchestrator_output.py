import sys
from pathlib import Path


backend_dir = Path(__file__).resolve().parents[1] / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.services.output_filter import strip_internal_agent_output  # noqa: E402


def test_strip_internal_agent_output_keeps_only_final_answer() -> None:
    raw = """1.任务拆解
识别用户输入为通用问候，无明确指定任务。

执行过程
输出友好应答。

合规审查
回应无违规内容。

最终产物
你好呀，我是 AgentHub 主控 Agent，可以随时告诉我你要完成的任务。
"""

    assert strip_internal_agent_output(raw) == "你好呀，我是 AgentHub 主控 Agent，可以随时告诉我你要完成的任务。"


def test_strip_internal_agent_output_passes_normal_reply() -> None:
    assert strip_internal_agent_output("你好，我可以帮你拆解和执行任务。") == "你好，我可以帮你拆解和执行任务。"
