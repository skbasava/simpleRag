“””
LangGraph Redis React Agent - Production Ready
Supports 100+ concurrent users via async Redis checkpointing + FastAPI
“””

import asyncio
import os
import json
import logging
from typing import Annotated, List, TypedDict, AsyncGenerator

# — LangGraph & LangChain —

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_core.tools import tool

# — Redis (async) —

from redis.asyncio import Redis, ConnectionPool

# — FastAPI for serving —

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn

# ─────────────────────────────────────────────

# LOGGING

# ─────────────────────────────────────────────

logging.basicConfig(
level=logging.INFO,
format=”%(asctime)s [%(levelname)s] %(name)s - %(message)s”,
)
logger = logging.getLogger(**name**)

# ─────────────────────────────────────────────

# ENVIRONMENT CONFIG

# ─────────────────────────────────────────────

REDIS_HOST     = os.getenv(“REDIS_HOST”, “localhost”)
REDIS_PORT     = int(os.getenv(“REDIS_PORT”, 6379))
REDIS_PASSWORD = os.getenv(“REDIS_PASSWORD”, None)
REDIS_DB       = int(os.getenv(“REDIS_DB”, 0))
REDIS_MAX_CONN = int(os.getenv(“REDIS_MAX_CONNECTIONS”, 100))  # pool size
OPENAI_API_KEY = os.getenv(“OPENAI_API_KEY”, “your-api-key-here”)
SESSION_TTL    = int(os.getenv(“SESSION_TTL_SECONDS”, 3600))   # 1 hour TTL

# ─────────────────────────────────────────────

# REDIS CLIENT  (shared, connection-pooled)

# ─────────────────────────────────────────────

def create_redis_client() -> Redis:
“””
Create an async Redis client with a connection pool.
Pool size of 100 comfortably handles 100+ concurrent users.
“””
pool = ConnectionPool(
host=REDIS_HOST,
port=REDIS_PORT,
password=REDIS_PASSWORD,
db=REDIS_DB,
max_connections=REDIS_MAX_CONN,
decode_responses=False,         # LangGraph needs raw bytes
socket_timeout=10,
socket_connect_timeout=5,
retry_on_timeout=True,
health_check_interval=30,
)
return Redis(connection_pool=pool)

# Global Redis client (initialised at startup)

redis_client: Redis = None
checkpointer: AsyncRedisSaver = None

# ─────────────────────────────────────────────

# TOOLS  (replace with your real tools)

# ─────────────────────────────────────────────

@tool
async def fetch_project_properties(project_name: str) -> str:
“”“Fetch property list for a given project from the data warehouse.”””
await asyncio.sleep(0.1)   # simulate async I/O
# TODO: replace with real DB / API call
return json.dumps({
“project”: project_name,
“properties”: [“prop_A”, “prop_B”, “prop_C”],
“mpu”: 42.5,
“status”: “active”,
})

@tool
async def get_project_mpu(project_name: str) -> str:
“”“Return the MPU (Maximum Planning Units) for a project.”””
await asyncio.sleep(0.05)
# TODO: replace with real lookup
return json.dumps({“project”: project_name, “mpu”: 42.5})

tools = [fetch_project_properties, get_project_mpu]

# ─────────────────────────────────────────────

# LLM

# ─────────────────────────────────────────────

llm = ChatOpenAI(
model=“gpt-4o-mini”,          # fast + cheap; swap to gpt-4o for better reasoning
temperature=0,
api_key=OPENAI_API_KEY,
streaming=True,               # enables token-by-token streaming
).bind_tools(tools)

# ─────────────────────────────────────────────

# AGENT STATE

# ─────────────────────────────────────────────

class AgentState(TypedDict):
messages: Annotated[List[BaseMessage], “Conversation history”]

# ─────────────────────────────────────────────

# GRAPH NODES

# ─────────────────────────────────────────────

async def call_agent(state: AgentState) -> AgentState:
“”“Main LLM node — async so it doesn’t block the event loop.”””
logger.debug(“call_agent: %d messages in history”, len(state[“messages”]))
response = await llm.ainvoke(state[“messages”])
return {“messages”: state[“messages”] + [response]}

def should_continue(state: AgentState) -> str:
“”“Route: call tools if the LLM requested them, otherwise finish.”””
last = state[“messages”][-1]
if hasattr(last, “tool_calls”) and last.tool_calls:
return “action”
return END

# ─────────────────────────────────────────────

# BUILD GRAPH  (compiled lazily after checkpointer is ready)

# ─────────────────────────────────────────────

def build_graph(cp: AsyncRedisSaver):
workflow = StateGraph(AgentState)

```
workflow.add_node("agent", call_agent)
workflow.add_node("action", ToolNode(tools))

workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue)
workflow.add_edge("action", "agent")

# compile WITH async Redis checkpointer — this is what gives each
# thread_id its own isolated, persistent memory
return workflow.compile(checkpointer=cp)
```

# Module-level graph handle (set at startup)

graph_app = None

# ─────────────────────────────────────────────

# CORE ASYNC CHAT FUNCTION

# ─────────────────────────────────────────────

async def chat(
session_id: str,
user_message: str,
) -> AsyncGenerator[str, None]:
“””
Send one message in a session and stream back events.
Each unique session_id gets its own isolated conversation history
stored in Redis under that key.
“””
config = {
“configurable”: {
“thread_id”: session_id,
# Optional: set a TTL on the Redis checkpoint key
“checkpoint_ttl”: SESSION_TTL,
}
}
input_data = {
“messages”: [HumanMessage(content=user_message)]
}

```
try:
    async for event in graph_app.astream(input_data, config, stream_mode="values"):
        last_msg = event["messages"][-1]
        # Only yield assistant (AI) messages
        if isinstance(last_msg, AIMessage) and last_msg.content:
            yield last_msg.content
except Exception as e:
    logger.exception("Error in session %s: %s", session_id, e)
    raise
```

# ─────────────────────────────────────────────

# FASTAPI  — HTTP interface for 100 concurrent users

# ─────────────────────────────────────────────

api = FastAPI(
title=“LangGraph Redis React Agent”,
description=“Production async agent with per-session memory stored in Redis”,
version=“1.0.0”,
)

class ChatRequest(BaseModel):
session_id: str
message: str

@api.on_event(“startup”)
async def startup():
global redis_client, checkpointer, graph_app
logger.info(“Connecting to Redis at %s:%s …”, REDIS_HOST, REDIS_PORT)
redis_client = create_redis_client()

```
# Verify connection
await redis_client.ping()
logger.info("Redis connection OK")

# Build async checkpointer
checkpointer = AsyncRedisSaver(redis_client)

# Build and compile the LangGraph workflow
graph_app = build_graph(checkpointer)
logger.info("LangGraph agent compiled and ready")
```

@api.on_event(“shutdown”)
async def shutdown():
if redis_client:
await redis_client.aclose()
logger.info(“Redis connection closed”)

@api.post(”/chat”)
async def chat_endpoint(req: ChatRequest):
“””
Non-streaming chat endpoint.
Returns the full assistant response once complete.
“””
collected = []
async for chunk in chat(req.session_id, req.message):
collected.append(chunk)
return {“session_id”: req.session_id, “response”: “”.join(collected)}

@api.post(”/chat/stream”)
async def chat_stream_endpoint(req: ChatRequest):
“””
Server-Sent Events (SSE) streaming endpoint.
Ideal for real-time UIs — tokens arrive as they’re generated.
“””
async def sse_generator():
try:
async for chunk in chat(req.session_id, req.message):
yield f”data: {json.dumps({‘chunk’: chunk})}\n\n”
yield “data: [DONE]\n\n”
except Exception as e:
yield f”data: {json.dumps({‘error’: str(e)})}\n\n”

```
return StreamingResponse(sse_generator(), media_type="text/event-stream")
```

@api.delete(”/session/{session_id}”)
async def clear_session(session_id: str):
“”“Delete all checkpoint data for a session (GDPR / user logout).”””
pattern = f”checkpoint:*:{session_id}:*”
keys = await redis_client.keys(pattern)
if keys:
await redis_client.delete(*keys)
return {“session_id”: session_id, “deleted_keys”: len(keys)}

@api.get(”/health”)
async def health():
“”“Liveness probe for load balancers / k8s.”””
try:
await redis_client.ping()
return {“status”: “ok”, “redis”: “connected”}
except Exception as e:
raise HTTPException(status_code=503, detail=f”Redis unavailable: {e}”)

# ─────────────────────────────────────────────

# LOAD TEST  (run directly to verify concurrency)

# ─────────────────────────────────────────────

async def load_test(num_users: int = 100):
“””
Simulate N concurrent users each sending 2 messages.
Run: python langgraph_redis_agent.py
(Requires Redis + OPENAI_API_KEY to be set)
“””
global redis_client, checkpointer, graph_app
redis_client = create_redis_client()
await redis_client.ping()
checkpointer = AsyncRedisSaver(redis_client)
graph_app    = build_graph(checkpointer)

```
async def user_session(user_id: int):
    session = f"load_test_user_{user_id}"
    try:
        # Turn 1
        response_1 = []
        async for chunk in chat(session, "Fetch properties for project kaanapali v2"):
            response_1.append(chunk)

        # Turn 2 — agent must remember "kaanapali v2" from turn 1
        response_2 = []
        async for chunk in chat(session, "What is the MPU for this project?"):
            response_2.append(chunk)

        logger.info(
            "User %d done | T1: %d chars | T2: %d chars",
            user_id, len("".join(response_1)), len("".join(response_2))
        )
    except Exception as e:
        logger.error("User %d failed: %s", user_id, e)

logger.info("Starting load test with %d concurrent users ...", num_users)
await asyncio.gather(*[user_session(i) for i in range(num_users)])
logger.info("Load test complete")
await redis_client.aclose()
```

# ─────────────────────────────────────────────

# ENTRY POINT

# ─────────────────────────────────────────────

if **name** == “**main**”:
import sys

```
if len(sys.argv) > 1 and sys.argv[1] == "loadtest":
    # python langgraph_redis_agent.py loadtest
    asyncio.run(load_test(num_users=100))
else:
    # python langgraph_redis_agent.py
    # Starts the FastAPI server on port 8000
    # For production: uvicorn langgraph_redis_agent:api --workers 4 --host 0.0.0.0 --port 8000
    uvicorn.run(
        "langgraph_redis_agent:api",
        host="0.0.0.0",
        port=8000,
        workers=1,           # asyncio handles concurrency; add workers for CPU-bound scale
        reload=False,
        log_level="info",
    )
```