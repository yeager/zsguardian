"""MCP client that spawns zscaler-mcp-server and communicates via stdio JSON-RPC."""

import asyncio
import json
import logging
import os
import signal
from dataclasses import dataclass, field
from typing import Any

from keychain import ZscalerCredentials

logger = logging.getLogger(__name__)
ZSCALER_MCP_VERSION = "0.15.4"


class MCPToolError(RuntimeError):
    """An MCP request or tool invocation failed."""


@dataclass
class MCPTool:
    name: str
    description: str = ""
    input_schema: dict = field(default_factory=dict)


class ZscalerMCPClient:
    """Manages the lifecycle of a zscaler-mcp subprocess and JSON-RPC communication."""

    def __init__(self, credentials: ZscalerCredentials, *, write_tools: str = ""):
        self.credentials = credentials
        self.write_tools = write_tools.strip()
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._tools: list[MCPTool] = []
        self._connected = False
        self._buffer = ""

    @property
    def connected(self) -> bool:
        return self._connected and self._process is not None and self._process.returncode is None

    @property
    def tools(self) -> list[MCPTool]:
        return list(self._tools)

    async def connect(self) -> bool:
        if self.connected:
            return True

        env = os.environ.copy()
        env.update(self.credentials.as_env())
        env["ZSCALER_MCP_WRITE_ENABLED"] = "true" if self.write_tools else "false"
        env["ZSCALER_MCP_WRITE_TOOLS"] = self.write_tools

        try:
            self._process = await asyncio.create_subprocess_exec(
                "uvx", "--from", f"zscaler-mcp=={ZSCALER_MCP_VERSION}", "zscaler-mcp",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                limit=1024 * 1024,  # 1MB buffer — tools/list response is ~170KB
                start_new_session=True,
            )
        except FileNotFoundError:
            logger.error("uvx not found — install uv first: https://docs.astral.sh/uv/")
            return False
        except Exception as e:
            logger.error("Failed to spawn zscaler-mcp: %s", e)
            return False

        self._reader_task = asyncio.create_task(self._read_loop())
        self._stderr_task = asyncio.create_task(self._drain_stderr())

        # Initialize MCP session
        result = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "ZSGuardian", "version": "1.0.0"},
        })

        if result is None:
            logger.error("MCP initialize failed")
            await self.disconnect()
            return False
        if isinstance(result, dict) and "_rpc_error" in result:
            logger.error("MCP initialize failed: %s", result["_rpc_error"])
            await self.disconnect()
            return False

        # Send initialized notification
        await self._send_notification("notifications/initialized", {})

        # Discover tools
        tools_result = await self._send_request("tools/list", {})
        if not isinstance(tools_result, dict) or not isinstance(tools_result.get("tools"), list):
            logger.error("MCP tools/list failed or returned an invalid response")
            await self.disconnect()
            return False
        if tools_result and "tools" in tools_result:
            self._tools = [
                MCPTool(
                    name=t["name"],
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {}),
                )
                for t in tools_result["tools"]
            ]
            logger.info("Discovered %d MCP tools", len(self._tools))

        self._connected = True
        return True

    async def disconnect(self):
        self._connected = False
        background_tasks = [task for task in (self._reader_task, self._stderr_task) if task]
        for task in background_tasks:
            task.cancel()
        self._reader_task = None
        self._stderr_task = None
        if background_tasks:
            await asyncio.gather(*background_tasks, return_exceptions=True)
        if self._process:
            process = self._process
            try:
                if process.stdin:
                    try:
                        process.stdin.close()
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                self._signal_process_group(process.pid, signal.SIGTERM)
                await asyncio.wait_for(process.wait(), timeout=5)
            except (asyncio.TimeoutError, ProcessLookupError):
                self._signal_process_group(process.pid, signal.SIGKILL)
                await process.wait()
            self._process = None
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()

    def terminate_now(self):
        """Stop the uvx process group during synchronous application shutdown."""
        if self._process and self._process.returncode is None:
            self._signal_process_group(self._process.pid, signal.SIGTERM)

    @staticmethod
    def _signal_process_group(pid: int, sig: int):
        try:
            os.killpg(pid, sig)
        except ProcessLookupError:
            pass

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        result = await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments or {},
        })
        if isinstance(result, dict) and "_rpc_error" in result:
            raise MCPToolError(f"RPC error calling {name}: {result['_rpc_error']}")
        if isinstance(result, dict) and result.get("isError"):
            detail = "\n".join(
                item.get("text", "") for item in result.get("content", [])
                if isinstance(item, dict) and item.get("type") == "text"
            )
            raise MCPToolError(detail or f"Tool {name} returned an MCP error")
        if result and "content" in result:
            texts = [c.get("text", "") for c in result["content"] if c.get("type") == "text"]
            combined = "\n".join(texts)
            try:
                return json.loads(combined)
            except (json.JSONDecodeError, ValueError):
                return combined
        return result

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _send_request(self, method: str, params: dict) -> Any | None:
        req_id = self._next_id()
        message = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future

        try:
            await self._write_message(message)
            return await asyncio.wait_for(future, timeout=60)
        except asyncio.TimeoutError:
            logger.warning("Request %s (id=%d) timed out", method, req_id)
            self._pending.pop(req_id, None)
            return None
        except Exception as e:
            logger.error("Request %s failed: %s", method, e)
            self._pending.pop(req_id, None)
            return None

    async def _send_notification(self, method: str, params: dict):
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        await self._write_message(message)

    async def _write_message(self, message: dict):
        if not self._process or not self._process.stdin:
            return
        data = json.dumps(message)
        self._process.stdin.write(data.encode("utf-8") + b"\n")
        await self._process.stdin.drain()

    async def _read_loop(self):
        try:
            while self._process and self._process.stdout:
                line = await self._process.stdout.readline()
                if not line:
                    break
                line_str = line.decode("utf-8").strip()
                if not line_str:
                    continue
                try:
                    msg = json.loads(line_str)
                except json.JSONDecodeError:
                    continue

                if "id" in msg and msg["id"] in self._pending:
                    future = self._pending.pop(msg["id"])
                    if not future.done():
                        if "error" in msg:
                            future.set_result({"_rpc_error": msg["error"]})
                            logger.error("RPC error: %s", msg["error"])
                        else:
                            future.set_result(msg.get("result"))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Reader loop error: %s", e)
        finally:
            self._connected = False

    async def _drain_stderr(self):
        """Keep the child stderr pipe flowing without logging arbitrary output."""
        try:
            while self._process and self._process.stderr:
                chunk = await self._process.stderr.read(65536)
                if not chunk:
                    break
                # Drain output to prevent pipe backpressure without copying
                # arbitrary child output (which could contain credentials) to logs.
                del chunk
        except asyncio.CancelledError:
            pass
