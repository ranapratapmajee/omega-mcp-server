import importlib
import inspect
import logging
import pkgutil
from abc import ABC, abstractmethod
from typing import Any, Dict, Type
from pydantic import BaseModel

logger = logging.getLogger("omega-mcp-server.registry")


class BaseTool(ABC):
    name: str
    description: str
    args_schema: Type[BaseModel]

    @abstractmethod
    async def run(self, **kwargs: Any) -> Any:
        pass


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            logger.warning("Tool '%s' is already registered. Overwriting.", tool.name)
        self._tools[tool.name] = tool
        logger.info("Registered tool: '%s'", tool.name)

    def autodiscover(self, package) -> None:
        for _, module_name, is_pkg in pkgutil.iter_modules(package.__path__):
            if is_pkg or module_name.startswith("_"):
                continue

            full_mod_name = f"{package.__name__}.{module_name}"
            module = importlib.import_module(full_mod_name)

            for _, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BaseTool) and obj is not BaseTool:
                    self.register(obj())

    def bind_to_mcp(self, mcp_server: Any) -> None:
        """Adapter: binds tool.run directly so MCP framework inspects its exact typed parameters."""
        for tool in self._tools.values():
            # If tool.run has explicit arguments matching the tool's inputs,
            # bind tool.run directly to preserve parameter names, types, and defaults.
            mcp_server.tool(name=tool.name, description=tool.description)(tool.run)