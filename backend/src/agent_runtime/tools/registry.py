"""
工具注册表

管理可用工具的注册和查询。
"""

from typing import Dict, List, Any, Callable, Optional


class ToolRegistry:
    """工具注册表"""

    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._handlers: Dict[str, Callable] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: Callable,
    ):
        """注册工具"""
        self._tools[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
        }
        self._handlers[name] = handler

    def get_tool(self, name: str) -> Optional[Dict[str, Any]]:
        """获取工具定义"""
        return self._tools.get(name)

    def get_handler(self, name: str) -> Optional[Callable]:
        """获取工具处理器"""
        return self._handlers.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        """列出所有工具（用于传递给 LLM）"""
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": info["description"],
                    "parameters": info["parameters"],
                },
            }
            for name, info in self._tools.items()
        ]

    def unregister(self, name: str):
        """注销工具"""
        self._tools.pop(name, None)
        self._handlers.pop(name, None)
