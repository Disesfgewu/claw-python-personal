import asyncio
from .registry import tool


@tool(
    name="bash",
    description="在 host 上執行 bash 指令，回傳 stdout + stderr",
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要執行的 bash 指令"
            },
            "timeout": {
                "type": "integer",
                "description": "逾時秒數，預設 30",
                "default": 30
            }
        },
        "required": ["command"]
    },
    requires_main=True,   # Phase 2 前只能在 main session 用
)
async def bash_tool(command: str, timeout: int = 30) -> str:
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = stdout.decode("utf-8", errors="replace")
        exit_code = proc.returncode
        if exit_code != 0:
            return f"[exit {exit_code}]\n{output}"
        return output
    except asyncio.TimeoutError:
        return f"Error: command timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"
