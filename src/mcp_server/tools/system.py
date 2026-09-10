import platform
import psutil
from pydantic import BaseModel, Field
from mcp_server.common import AgentResponse
from mcp_server.registry import BaseTool


class SystemStatusInput(BaseModel):
    include_memory: bool = Field(
        default=True, description="Whether to include RAM metrics"
    )


class SystemStatusTool(BaseTool):
    name = "get_system_status"
    description = "Retrieve current host operating system and hardware resource statistics."
    args_schema = SystemStatusInput

    async def run(self, include_memory: bool = True) -> dict:
        try:
            data = {
                "os": platform.system(),
                "cpu_percent": psutil.cpu_percent(interval=None),
            }
            if include_memory:
                mem = psutil.virtual_memory()
                data["memory_percent"] = mem.percent

            return AgentResponse.ok(
                data=data, summary="Host metrics retrieved successfully."
            ).model_dump()
        except Exception as e:
            return AgentResponse.fail(str(e)).model_dump()