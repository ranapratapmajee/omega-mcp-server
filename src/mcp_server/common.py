from typing import Any, Optional
from pydantic import BaseModel, Field


class AgentResponse(BaseModel):
    success: bool = Field(..., description="Whether the tool execution succeeded")
    data: Optional[Any] = Field(default=None, description="Structured result data")
    error: Optional[str] = Field(default=None, description="Error details if execution failed")
    summary: Optional[str] = Field(default=None, description="Concise natural language summary for LLM context")

    @classmethod
    def ok(cls, data: Any = None, summary: Optional[str] = None) -> "AgentResponse":
        return cls(success=True, data=data, error=None, summary=summary)

    @classmethod
    def fail(cls, message: str, summary: Optional[str] = None) -> "AgentResponse":
        return cls(success=False, data=None, error=message, summary=summary)