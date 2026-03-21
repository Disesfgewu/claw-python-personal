from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from claw.core.config import get_config

try:
    import docker
    import docker.errors as docker_errors
except Exception:  # pragma: no cover - optional dependency in tests
    docker = None
    docker_errors = None

logger = logging.getLogger(__name__)


@dataclass
class SandboxContainer:
    session_id: str
    container_id: str
    workspace_path: str
    created_at: float


class DockerRunner:
    """
    Per-session Docker container 管理。
    每個 session 最多一個 container，重複使用到 session 結束。
    """

    def __init__(self):
        self._client = None
        self._containers: dict[str, SandboxContainer] = {}
        self._lock = asyncio.Lock()

    def _get_client(self):
        if docker is None:
            raise RuntimeError("docker package is not available")
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    async def run(
        self,
        session_id: str,
        command: str,
        timeout: int | None = None,
    ) -> str:
        """
        在 session 對應的 sandbox container 內執行 bash 指令。
        Container 不存在時自動建立。
        回傳 stdout + stderr 合併字串。
        """
        cfg = get_config().sandbox
        effective_timeout = timeout or cfg.timeout

        async with self._lock:
            container = await self._ensure_container(session_id)

        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, self._exec_in_container, container, command),
            timeout=effective_timeout + 5,
        )
        return result

    async def destroy(self, session_id: str) -> None:
        """刪除 session 對應的 container"""
        async with self._lock:
            sandbox = self._containers.pop(session_id, None)
        if sandbox:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._remove_container, sandbox.container_id)

    async def destroy_all(self) -> None:
        """清理所有 container（shutdown 時呼叫）"""
        async with self._lock:
            ids = list(self._containers.keys())
        for sid in ids:
            await self.destroy(sid)

    async def _ensure_container(self, session_id: str) -> SandboxContainer:
        """如果 container 不存在或已停止，重新建立"""
        existing = self._containers.get(session_id)
        if existing:
            try:
                c = self._get_client().containers.get(existing.container_id)
                if c.status == "running":
                    return existing
            except Exception as e:
                if docker_errors and isinstance(e, docker_errors.NotFound):
                    pass
                else:
                    pass
            self._containers.pop(session_id, None)

        container = await asyncio.get_event_loop().run_in_executor(
            None, self._create_container, session_id
        )
        self._containers[session_id] = container
        return container

    def _create_container(self, session_id: str) -> SandboxContainer:
        import os
        import time
        from pathlib import Path

        cfg = get_config().sandbox
        client = self._get_client()

        workspace = os.path.expanduser(
            f"~/.claw/workspaces/{session_id.replace(':', '_')}"
        )
        os.makedirs(workspace, exist_ok=True)

        # Security options
        security_opt = ["no-new-privileges:true"]
        seccomp_path = Path(__file__).parent / "seccomp_minimal.json"
        if seccomp_path.exists():
            security_opt.append(f"seccomp={seccomp_path}")

        # Memory: support both old string format ("256m") and new integer (400)
        memory_mb = getattr(cfg, "memory_limit_mb", None)
        if memory_mb is None:
            mem_str = getattr(cfg, "memory_limit", "256m")
            memory_mb = int(str(mem_str).rstrip("mM"))

        cpus = float(getattr(cfg, "cpus", 1.5))
        tmp_size_mb = int(getattr(cfg, "tmp_size_mb", 128))

        container = client.containers.run(
            image=cfg.image,
            command="/bin/bash",
            detach=True,
            tty=True,
            stdin_open=True,
            working_dir=cfg.workspace_dir,
            volumes={workspace: {"bind": cfg.workspace_dir, "mode": "rw"}},
            mem_limit=f"{memory_mb}m",
            memswap_limit=f"{memory_mb}m",
            nano_cpus=int(cpus * 1e9),
            network_mode="none",
            read_only=True,
            tmpfs={
                "/tmp": f"size={tmp_size_mb}m,noexec,nosuid",
                "/run": "size=8m,noexec,nosuid",
                "/var/tmp": "size=8m,noexec,nosuid",
            },
            security_opt=security_opt,
            user="nobody",
            remove=False,
            labels={"claw.session_id": session_id},
        )
        logger.info(
            f"sandbox created (hardened): {container.short_id} "
            f"mem={memory_mb}m cpus={cpus} "
            f"seccomp={'yes' if seccomp_path.exists() else 'no'} "
            f"for {session_id}"
        )
        return SandboxContainer(
            session_id=session_id,
            container_id=container.id,
            workspace_path=workspace,
            created_at=time.time(),
        )

    def _exec_in_container(self, sandbox: SandboxContainer, command: str) -> str:
        """Blocking：在 container 內執行指令"""
        cfg = get_config().sandbox
        client = self._get_client()
        try:
            container = client.containers.get(sandbox.container_id)
            result = container.exec_run(
                cmd=["bash", "-c", command],
                workdir=cfg.workspace_dir,
                demux=False,
                user="sandbox",
            )
            output = (result.output or b"").decode("utf-8", errors="replace")
            exit_code = result.exit_code
            if exit_code != 0:
                return f"[exit {exit_code}]\n{output}"
            return output
        except Exception as e:
            if docker_errors and isinstance(e, docker_errors.NotFound):
                return "Error: container not found"
            return f"Error: {e}"

    def _remove_container(self, container_id: str) -> None:
        try:
            c = self._get_client().containers.get(container_id)
            c.stop(timeout=3)
            c.remove(force=True)
            logger.info(f"sandbox removed: {container_id[:12]}")
        except Exception as e:
            if docker_errors and isinstance(e, docker_errors.NotFound):
                return
            logger.warning(f"sandbox remove error: {e}")


_runner: DockerRunner | None = None


def get_runner() -> DockerRunner:
    global _runner
    if _runner is None:
        _runner = DockerRunner()
    return _runner
