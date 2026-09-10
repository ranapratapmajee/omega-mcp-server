# Omega MCP Server

A modular, production-grade Model Context Protocol (MCP) server built with Python (`mcp 2.x`) and `MCPServer`. Designed to serve reusable, self-documenting tools to autonomous agents, multi-agent frameworks, and external services over **Server-Sent Events (SSE)** using an enterprise-ready **Class-Based Tool Registry**.

---

## 1. Architectural Overview

Omega MCP Server acts as a centralized, decoupled tool provider across consumer projects:

- **SSE Transport:** Exposes an SSE stream at `/sse` and a JSON-RPC execution endpoint at `/messages/`.
- **Class-Based Registry Pattern:** Every tool inherits from an abstract `BaseTool` class, enforcing schema validation via Pydantic and explicit typing without circular dependencies.
- **Dynamic Auto-Discovery:** Modules placed inside `src/mcp_server/tools/` are scanned and loaded via Python reflection (`pkgutil` and `inspect`) on startup.
- **Predictable Agent Envelope:** All tools wrap execution output in a typed `AgentResponse` contract (`success`, `data`, `error`, `summary`) tailored for LLM reasoning loops.

```text
┌─────────────────────────────────────────────────────────────┐
│  Client Projects (LangGraph, CrewAI, Custom Agents, IDEs)   │
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

Agents require deterministic output formats to reliably decide whether to continue execution, retry, or surface findings. All tools return the `AgentResponse` contract defined in `src/mcp_server/common.py`.

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
| `data` | `dict | list | null` | Machine-readable payload for downstream tasks or LLM analysis. |
| `error` | `string | null` | Error trace or message on failure; `null` on success. |
| `summary` | `string | null` | Short summary for LLM context windows and chain-of-thought steps. |

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
│   └── mcp_client_test.py     # End-to-end verification client test script
└── src/
    └── mcp_server/
        ├── __init__.py
        ├── common.py          # Standard AgentResponse contract model
        ├── registry.py        # BaseTool ABC & ToolRegistry engine
        ├── server.py          # MCPServer bootstrap & adapter binding
        └── tools/             # Class-based tool modules (drop new tools here)
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

1. **Build and start the container:**
```bash
docker compose up --build -d

```


2. **Inspect logs and verify loaded tools:**
```bash
docker compose logs -f

```


3. **Verify the SSE stream:**
```bash
curl -N http://localhost:8080/sse

```



---

## 5. Adding New Tools Over Time

The server uses an auto-discovery engine. Adding a new tool requires **zero modifications** to `server.py` or `registry.py`.

### The 4 Rules Every Tool Must Follow

1. **Inherit from `BaseTool`:** Subclass `BaseTool` from `mcp_server.registry`.
2. **Define an Explicit Input Schema:** Create a Pydantic `BaseModel` using `Field(..., description="...")` for every parameter so LLMs understand valid inputs.
3. **Set Class Attributes:** Provide `name`, `description`, and `args_schema`.
4. **Wrap Outputs in `AgentResponse`:** Always wrap successful returns in `AgentResponse.ok()` and catch exceptions with `AgentResponse.fail()`.

---

### Step-by-Step Example: Adding a Database Tool

Create a new file: `src/mcp_server/tools/database.py`:

```python
from typing import Any
from pydantic import BaseModel, Field
from mcp_server.common import AgentResponse
from mcp_server.registry import BaseTool


# Step 1: Define the strict input schema for LLM agents
class QueryRecordsInput(BaseModel):
    table: str = Field(..., description="Target database table to read from")
    limit: int = Field(default=10, description="Maximum number of records to return")


# Step 2: Implement the tool subclassing BaseTool
class QueryRecordsTool(BaseTool):
    name = "query_records"
    description = "Query structured records from a specified database table."
    args_schema = QueryRecordsInput

    async def run(self, table: str, limit: int = 10) -> dict:
        try:
            # Execution logic (e.g. database client query)
            records = [{"id": i, "table": table} for i in range(1, limit + 1)]

            return AgentResponse.ok(
                data={"rows": records, "count": len(records)},
                summary=f"Retrieved {len(records)} records from '{table}'."
            ).model_dump()

        except Exception as exc:
            return AgentResponse.fail(str(exc)).model_dump()

```

### Reloading After Adding a Tool

* **Local Dev:** Restart the server process (`uv run python -m mcp_server.server`).
* **Docker:** Run `docker compose restart`.

The registry dynamically discovers `QueryRecordsTool`, extracts its parameter types, and exposes it over `/sse`.

---

## 6. Client Integration via SSE

External projects interact with Omega MCP Server through the SSE URL:

```text
http://<host>:8080/sse

```

### Python Client Example (`scripts/mcp_client_test.py`)

```python
import asyncio
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client


async def main():
    async with sse_client("http://localhost:8080/sse") as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            # 1. Discover registered tools
            tools = await session.list_tools()
            print("Available Tools:", [t.name for t in tools.tools])

            # 2. Call a tool
            result = await session.call_tool(
                "get_system_status",
                arguments={"include_memory": True}
            )
            print("\nTool Output:", result.content[0].text)


if __name__ == "__main__":
    asyncio.run(main())

```

### IDE / Developer Tool Configuration (Claude Desktop, Cursor)

```json
{
  "mcpServers": {
    "omega-mcp": {
      "url": "http://localhost:8080/sse"
    }
  }
}

```

---

## 7. Calling Tools from Other Agentic AI Projects

When integrating Omega MCP Server tools into external agent pipelines, choose the integration method suited to your tech stack:

### Pattern A: LangChain & LangGraph Agents

Use `langchain-mcp-adapters` to automatically convert Omega MCP tools into LangChain tools for agents.

**1. Install dependency in the agent project:**

```bash
uv add langchain-mcp-adapters langchain-openai

```

**2. Load tools into an agent loop:**

```python
import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI


async def run_agent():
    async with MultiServerMCPClient(
        {
            "omega_server": {
                "url": "http://localhost:8080/sse",
                "transport": "sse",
            }
        }
    ) as client:
        # Automatically converts MCP tools to LangChain BaseTools
        tools = client.get_tools()

        llm = ChatOpenAI(model="gpt-4o-mini")
        agent = llm.bind_tools(tools)

        # Agent decides to invoke 'get_system_status' or 'calculate_sum'
        response = await agent.ainvoke("Check current system metrics and calculate 42 * 8.")
        print(response)


if __name__ == "__main__":
    asyncio.run(run_agent())

```

---

### Pattern B: Custom Python Agent / Microservice (Reusable Wrapper)

For custom agents that need fine-grained control over tool execution and `AgentResponse` parsing without external agent frameworks:

```python
import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any, Dict
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client


class OmegaToolClient:
    """Reusable client for invoking Omega MCP tools over SSE."""

    def __init__(self, sse_url: str = "http://localhost:8080/sse"):
        self.sse_url = sse_url

    @asynccontextmanager
    async def session(self):
        async with sse_client(self.sse_url) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as sess:
                await sess.initialize()
                yield sess

    async def list_available_tools(self) -> list[Dict[str, Any]]:
        async with self.session() as sess:
            res = await sess.list_tools()
            return [
                {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.inputSchema,
                }
                for t in res.tools
            ]

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        async with self.session() as sess:
            result = await sess.call_tool(tool_name, arguments=arguments)
            raw_payload = result.content[0].text
            # Parse standardized AgentResponse JSON
            return json.loads(raw_payload)


# Example execution inside an agent loop
async def main():
    client = OmegaToolClient("http://localhost:8080/sse")

    # Fetch available tool definitions for LLM prompt/tool-binding
    tools = await client.list_available_tools()
    print("Fetched tools for agent:", [t["name"] for t in tools])

    # Invoke tool directly when the agent makes a tool-call decision
    response = await client.execute_tool(
        "calculate_sum",
        arguments={"a": 10.5, "b": 22.3}
    )

    if response.get("success"):
        print("Tool Output:", response["data"])
        print("Summary for Context:", response["summary"])
    else:
        print("Tool Failed:", response["error"])


if __name__ == "__main__":
    asyncio.run(main())

```

---

### Pattern C: Docker-to-Docker Integration (Containerized Agents)

When your agent runs in another Docker container on the same host machine, communicate via a shared Docker network instead of `localhost`:

1. **Create a shared network:**
```bash
docker network create ai-network

```


2. **Connect Omega MCP Server (`docker-compose.yaml`):**
```yaml
services:
  omega-mcp-server:
    # ...
    networks:
      - ai-network

networks:
  ai-network:
    external: true

```


3. **In the agent container, connect using the service name:**
```python
client = OmegaToolClient(sse_url="http://omega_mcp_server:8080/sse")

```



---

## 8. Common Operations

| Command | Action |
| --- | --- |
| `uv run python -m mcp_server.server` | Start local server with `uv` |
| `uv run python -m scripts.mcp_client_test` | Run verification client test script |
| `docker compose up --build -d` | Build and run server in background |
| `docker compose logs -f` | Tail container startup and tool registration logs |
| `docker compose restart` | Restart server to reload newly added tools |
| `docker compose down` | Stop containerized server |
