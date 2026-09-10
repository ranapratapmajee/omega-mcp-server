# Omega MCP Server

A modular, production-grade Model Context Protocol (MCP) server built with Python (`mcp 2.x`) and `MCPServer`. It exposes self-documenting, reusable tools to autonomous agents, multi-agent frameworks, and external services over **Server-Sent Events (SSE)** using an enterprise-ready **Class-Based Tool Registry**.

---

## 1. Architectural Overview

Omega MCP Server acts as a centralized tool provider across consumer projects:

- **SSE Transport:** Runs an HTTP service exposing an SSE stream at `/sse` and a JSON-RPC message endpoint at `/messages/`.
- **Class-Based Registry:** Every tool inherits from `BaseTool`, ensuring strict schema validation via Pydantic and eliminating circular import risks.
- **Dynamic Autodiscovery:** Modules placed in `src/mcp_server/tools/` are scanned and registered on startup using Python inspection (`pkgutil` and `inspect`).
- **Predictable Agent Envelope:** All tools wrap execution output in a typed `AgentResponse` contract (`success`, `data`, `error`, `summary`) optimized for LLM reasoning loops.

```text
┌─────────────────────────────────────────────────────────────┐
│  Client Projects (Custom Agents, LangGraph, CrewAI, IDEs)   │
└──────────────────────────────┬──────────────────────────────┘
                               │ SSE (http://<host>:8080/sse)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                      Omega MCP Server                       │
│                   (MCPServer SSE Engine)                    │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ ToolRegistry Engine (Dynamic Scanner & Binder)        │  │
│  │  ├── SystemStatusTool  (subclass of BaseTool)         │  │
│  │  ├── CalculateSumTool  (subclass of BaseTool)         │  │
│  │  └── <NewTool>         (subclass of BaseTool)         │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘

```

---

## 2. Standardized Agent Contract (`AgentResponse`)

Agents need deterministic responses to evaluate tool outcomes and plan subsequent actions. All tools return the `AgentResponse` schema defined in `src/mcp_server/common.py`.

### Response Schema

```json
{
  "success": true,
  "data": {
    "result_key": "result_value"
  },
  "error": null,
  "summary": "Concise natural language summary of what occurred."
}

```

### Field Definitions

| Field | Type | Description |
| --- | --- | --- |
| `success` | `bool` | Execution status flag. |
| `data` | `dict | list | str | null` | Machine-readable payload for downstream tasks or LLM reasoning. |
| `error` | `string | null` | Error message on failure; `null` on success. |
| `summary` | `string | null` | Brief summary for LLM context windows (optional). |

---

## 3. Project Structure

```text
omega-mcp-server/
├── Dockerfile
├── docker-compose.yaml
├── pyproject.toml
├── .dockerignore
├── README.md
├── scripts/
│   └── mcp_client_test.py     # Verification client test script
└── src/
    └── mcp_server/
        ├── __init__.py
        ├── common.py          # Standard AgentResponse contract model
        ├── registry.py        # BaseTool ABC & ToolRegistry engine
        ├── server.py          # MCPServer bootstrap & adapter binding
        └── tools/             # Class-based tool modules
            ├── __init__.py
            ├── system.py      # SystemStatusTool (host inspection)
            └── math.py        # CalculateSumTool (arithmetic computation)

```

---

## 4. Quick Start

### Running Locally with `uv`

1. **Install dependencies:**
```bash
uv sync

```


2. **Start the server:**
```bash
uv run python -m mcp_server.server

```


The server starts on `http://0.0.0.0:8080`.
3. **Verify with the test client:**
In a separate terminal:
```bash
uv run python -m scripts.mcp_client_test

```



---

### Running with Docker

1. **Build and launch the container:**
```bash
docker compose up --build -d

```


2. **Check logs and verify loaded tools:**
```bash
docker compose logs -f

```


3. **Inspect the SSE endpoint:**
```bash
curl -N http://localhost:8080/sse

```



---

## 5. Adding New Tools

The auto-discovery engine scans `src/mcp_server/tools/` on boot. Adding a tool requires no modifications to `server.py` or `registry.py`.

### The 4 Rules for Every Tool

1. **Subclass `BaseTool`:** Inherit from `BaseTool` in `mcp_server.registry`.
2. **Define an Input Schema:** Create a Pydantic `BaseModel` using `Field(..., description="...")` for each parameter.
3. **Set Class Attributes:** Provide `name`, `description`, and `args_schema`.
4. **Wrap Output in `AgentResponse`:** Return `AgentResponse.ok()` on success and catch exceptions with `AgentResponse.fail()`.

---

### Implementation Template: `src/mcp_server/tools/<tool_name>.py`

```python
from typing import Any
from pydantic import BaseModel, Field
from mcp_server.common import AgentResponse
from mcp_server.registry import BaseTool


# 1. Define input parameters and descriptions
class CustomToolInput(BaseModel):
    query: str = Field(..., description="Input query or target argument")
    limit: int = Field(default=5, description="Maximum number of items to return")


# 2. Implement the tool class
class CustomTool(BaseTool):
    name = "custom_tool"
    description = "Detailed explanation of what the tool accomplishes."
    args_schema = CustomToolInput

    async def run(self, query: str, limit: int = 5) -> dict:
        try:
            # Core execution logic
            result_payload = {"echo": query, "count": limit}

            return AgentResponse.ok(
                data=result_payload,
                summary=f"Processed query '{query}' with limit {limit}."
            ).model_dump()

        except Exception as exc:
            return AgentResponse.fail(str(exc)).model_dump()

```

### Reloading

* **Local:** Restart the process (`uv run python -m mcp_server.server`).
* **Docker:** Run `docker compose restart`.

---

## 6. Consuming Tools from External Agentic AI Projects

To keep agent workflows decoupled from MCP networking logic, use a two-layer structure:

1. `mcp_client.py`: Manages SSE transport, session lifecycle, and maps tools to standard callables.
2. `agent.py`: Imports and binds the callables directly into the agent.

---

### Step 1: Create the Reusable Client Adapter (`mcp_client.py`)

Place this file inside your consumer project. It connects over SSE, executes remote tools, and extracts the payload from `AgentResponse`.

```python
import asyncio
import json
import os
from typing import Any, Callable, Dict, List
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client

DEFAULT_SSE_URL = os.getenv("OMEGA_MCP_URL", "http://localhost:8080/sse")


class OmegaMCPClient:
    """Manages SSE connection and execution for remote MCP tools."""

    def __init__(self, sse_url: str = DEFAULT_SSE_URL):
        self.sse_url = sse_url

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Call remote tool over SSE and unwrap the AgentResponse envelope."""
        async with sse_client(self.sse_url) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                response = await session.call_tool(tool_name, arguments=arguments)
                raw_text = response.content[0].text

                try:
                    payload = json.loads(raw_text)
                    if not payload.get("success", False):
                        return f"Tool Error ({tool_name}): {payload.get('error')}"
                    return str(payload.get("data"))
                except (json.JSONDecodeError, AttributeError):
                    return raw_text

    async def list_tools(self) -> List[str]:
        """Query available tool names exposed by the server."""
        async with sse_client(self.sse_url) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                res = await session.list_tools()
                return [t.name for t in res.tools]


# Shared client instance
client = OmegaMCPClient()


def create_agent_tool(name: str, description: str = "") -> Callable:
    """Factory that produces a generic callable compatible with agent frameworks."""

    async def async_dispatch(**kwargs) -> str:
        return await client.execute_tool(name, kwargs)

    def dispatch(**kwargs) -> str:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(async_dispatch(**kwargs))
        else:
            return asyncio.run(async_dispatch(**kwargs))

    dispatch.__name__ = name
    dispatch.__doc__ = description or f"Executes the remote MCP tool '{name}'."
    return dispatch


# Map remote tools to standard Python callables
get_system_status = create_agent_tool(
    name="get_system_status",
    description="Retrieves current host CPU and memory usage statistics."
)

calculate_sum = create_agent_tool(
    name="calculate_sum",
    description="Calculates the sum of two numbers (a, b)."
)

```

---

### Step 2: Inject Tools into Your Agent (`agent.py`)

The agent imports the tool functions like native Python functions.

```python
import os
# Replace with your framework's imports (Google GenAI, LangChain, CrewAI, AutoGen, etc.)
from your_agent_framework import Agent, llm

# Import pre-configured callables from the MCP client adapter
from mcp_client import calculate_sum, get_system_status

generic_agent = Agent(
    name="GenericTaskAgent",
    description="Executes tasks using modular tools served over MCP.",
    model=llm,
    tools=[get_system_status, calculate_sum],
    instruction="""You are a task execution agent.
    When asked about system metrics or arithmetic operations, call the appropriate 
    registered tool and summarize the result cleanly for the user.
    """
)

if __name__ == "__main__":
    # Example invocation
    prompt = "Check current system resources and calculate 45 + 55."
    print(f"User Request: {prompt}\n")

    # Run agent according to your framework API:
    # response = generic_agent.run(prompt)
    # print(response)

```

---

### Step 3: Containerized Agent Communication (Docker-to-Docker)

When running both Omega MCP Server and your agent inside Docker, communicate using Docker's bridge network:

1. **Create a shared network:**
```bash
docker network create agent-network

```


2. **Attach Omega MCP Server in `docker-compose.yaml`:**
```yaml
services:
  omega-mcp-server:
    # ...
    networks:
      - agent-network

networks:
  agent-network:
    external: true

```


3. **In the agent container, set the environment variable:**
```bash
OMEGA_MCP_URL=http://omega_mcp_server:8080/sse

```



---

## 7. Common Operations

| Command | Action |
| --- | --- |
| `uv run python -m mcp_server.server` | Start local server with `uv` |
| `uv run python -m scripts.mcp_client_test` | Run verification client test script |
| `docker compose up --build -d` | Build and run server in background |
| `docker compose logs -f` | Tail container startup and tool registration logs |
| `docker compose restart` | Restart server to reload newly added tools |
| `docker compose down` | Stop containerized server |
