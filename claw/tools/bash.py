import asyncio
from .registry import tool
from claw.sandbox.policy import needs_sandbox


@tool(
    name="bash",
    description="執行 bash 指令。main session 在 host 執行；其他 session 在 Docker sandbox 執行。",
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
    requires_main=False,   # sandbox 後開放給所有 session
)
async def bash_tool(command: str, timeout: int = 30, session_id: str = "agent:main") -> str:
    if needs_sandbox(session_id):
        from claw.sandbox.docker_runner import get_runner
        runner = get_runner()
        # The runner returns a string which is what we want.
        return await runner.run(session_id, command, timeout=timeout)

    try:
        # Host execution for main session
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
