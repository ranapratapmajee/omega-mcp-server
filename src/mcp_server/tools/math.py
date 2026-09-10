from pydantic import BaseModel, Field
from mcp_server.common import AgentResponse
from mcp_server.registry import BaseTool


class MathSumInput(BaseModel):
    a: float = Field(..., description="First number")
    b: float = Field(..., description="Second number")


class CalculateSumTool(BaseTool):
    name = "calculate_sum"
    description = "Add two numbers together."
    args_schema = MathSumInput

    async def run(self, a: float, b: float) -> dict:
        try:
            total = a + b
            return AgentResponse.ok(
                data={"result": total}, summary=f"Sum of {a} and {b} is {total}"
            ).model_dump()
        except Exception as e:
            return AgentResponse.fail(str(e)).model_dump()