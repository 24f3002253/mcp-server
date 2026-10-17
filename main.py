import hashlib
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

EMAIL = "24f3002253@ds.study.iitm.ac.in".strip().lower()
SUPPORTED = ["2025-06-18", "2025-03-26", "2024-11-05"]

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Mcp-Session-Id"],
)

TOOL = {
    "name": "solve_challenge",
    "description": "Returns the response code for the current exam challenge, "
                   "read from the X-Exam-Challenge HTTP header.",
    "inputSchema": {"type": "object", "properties": {}},
}


def answer_for(challenge: str) -> str:
    return hashlib.sha256(f"{challenge}:{EMAIL}".encode()).hexdigest()[:16]


def ok(rid: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def err(rid: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def handle(msg: dict, headers) -> dict | None:
    method = msg.get("method")
    rid = msg.get("id")

    # Notifications (no id) get no JSON-RPC response.
    if rid is None and method and method.startswith("notifications/"):
        return None

    if method == "initialize":
        asked = (msg.get("params") or {}).get("protocolVersion")
        version = asked if asked in SUPPORTED else SUPPORTED[0]
        return ok(rid, {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "exam-mcp", "version": "1.0.0"},
        })
    if method == "ping":
        return ok(rid, {})
    if method == "tools/list":
        return ok(rid, {"tools": [TOOL]})
    if method == "tools/call":
        name = (msg.get("params") or {}).get("name")
        if name != "solve_challenge":
            return err(rid, -32602, f"Unknown tool: {name}")
        challenge = (headers.get("x-exam-challenge") or "").strip()
        if not challenge:
            return ok(rid, {
                "content": [{"type": "text", "text": "missing X-Exam-Challenge header"}],
                "isError": True,
            })
        return ok(rid, {"content": [{"type": "text", "text": answer_for(challenge)}]})
    if rid is None:
        return None
    return err(rid, -32601, f"Method not found: {method}")


@app.post("/mcp")
@app.post("/")
async def mcp(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(err(None, -32700, "Parse error"), status_code=400)

    if isinstance(body, list):
        results = [r for r in (handle(m, request.headers) for m in body) if r is not None]
        if not results:
            return Response(status_code=202)
        return JSONResponse(results)

    result = handle(body, request.headers)
    if result is None:
        return Response(status_code=202)
    return JSONResponse(result)


@app.get("/mcp")
async def mcp_get():
    return Response(status_code=405, headers={"Allow": "POST"})


@app.get("/health")
def health():
    return {"status": "ok"}