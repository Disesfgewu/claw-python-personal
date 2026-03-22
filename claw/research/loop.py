from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncIterator

from claw.research.experiment import ExperimentResult, ExperimentStatus
from claw.research.ledger import ResearchLedger
from claw.research.planner import ResearchPlanner

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ExperimentCompleted:
    result: ExperimentResult


@dataclass
class ResearchCompleted:
    task_id: str
    kept: list[ExperimentResult]
    reason: str


@dataclass
class ResearchExhausted:
    task_id: str
    kept: list[ExperimentResult]


ResearchEvent = ExperimentCompleted | ResearchCompleted | ResearchExhausted


class ResearchLoop:
    """
    Autonomous research loop. Orchestrates:
      Planner → execute → evaluate (A→C→B) → keep/discard → iterate
    """

    def __init__(
        self,
        llm,
        ledger: ResearchLedger | None = None,
        agent_loop=None,   # AgentLoop | None — 若提供則用於真實工具執行
    ):
        self.llm = llm
        self.ledger = ledger or ResearchLedger()
        self.planner = ResearchPlanner(llm)
        self.agent_loop = agent_loop  # Optional[AgentLoop]

    async def run(
        self,
        question: str,
        success_criteria: str | None = None,
        eval_cmd: str | None = None,
        max_experiments: int = 20,
        session_id: str = "agent:main",
    ) -> AsyncIterator[ResearchEvent]:
        task_id = await self.ledger.create_task(
            question, success_criteria, eval_cmd, max_experiments
        )
        logger.info(f"research.start task_id={task_id} question={question[:80]}")

        all_results: list[ExperimentResult] = []

        # Decompose question into initial hypotheses
        hypotheses = await self.planner.decompose(question)
        hypothesis_queue = list(hypotheses)

        for exp_num in range(max_experiments):
            # Pick next hypothesis
            if hypothesis_queue:
                hypothesis = hypothesis_queue.pop(0)
            else:
                hypothesis = await self.planner.next_hypothesis(question, all_results)

            # Execute the experiment via agent loop
            approach, output = await self._execute(hypothesis, session_id)

            # Run eval_cmd if provided (C layer)
            metric = await self._run_eval_cmd(eval_cmd) if eval_cmd else None

            # Three-layer evaluation
            status, reasoning = await self._evaluate(
                output, metric, success_criteria, eval_cmd, all_results
            )

            result = ExperimentResult(
                task_id=task_id,
                hypothesis=hypothesis,
                approach=approach,
                output=output,
                metric=metric,
                status=status,
                reasoning=reasoning,
                ts=_now(),
            )
            await self.ledger.record_experiment(result)
            all_results.append(result)
            yield ExperimentCompleted(result)

            # Check termination
            if status == ExperimentStatus.KEEP:
                terminate, reason = await self._should_terminate(
                    result, success_criteria, eval_cmd, all_results
                )
                if terminate:
                    await self.ledger.complete_task(task_id, "completed")
                    yield ResearchCompleted(task_id, [r for r in all_results if r.status == ExperimentStatus.KEEP], reason)
                    return

        await self.ledger.complete_task(task_id, "exhausted")
        yield ResearchExhausted(task_id, [r for r in all_results if r.status == ExperimentStatus.KEEP])

    async def _execute(self, hypothesis: str, session_id: str) -> tuple[str, str]:
        """
        Execute a research hypothesis.
        If agent_loop is available, use it (real tool calls).
        Otherwise fall back to direct LLM generation.
        """
        if self.agent_loop is not None:
            return await self._execute_via_agent(hypothesis, session_id)
        return await self._execute_via_llm(hypothesis)

    async def _execute_via_agent(self, hypothesis: str, session_id: str) -> tuple[str, str]:
        """Run hypothesis through AgentLoop so tools are available."""
        from claw.core.storage import SessionRow
        from claw.agent.events import TextChunk, ToolCallResult, RunComplete, RunError
        from datetime import datetime, timezone

        # Create a temporary sub-session for this experiment
        sub_session_id = f"research:{session_id}:{hypothesis[:20].replace(' ', '_')}"
        now = datetime.now(timezone.utc).isoformat()

        # Ensure sub-session exists in storage
        existing = await self.agent_loop.storage.get_session(sub_session_id)
        if existing is None:
            await self.agent_loop.storage.create_session(SessionRow(
                session_id=sub_session_id,
                scope="research",
                channel="internal",
                agent_id="research",
                system_prompt=None,
                queue_mode="collect",
                sandbox=False,
                created_at=now,
                last_active=now,
                config={},
            ))

        prompt = (
            f"Research hypothesis to investigate:\n\n"
            f"{hypothesis}\n\n"
            f"Use available tools (web_fetch, bash, file_read, memory_search) as needed. "
            f"Report your findings concisely in 2-3 sentences."
        )

        text_parts: list[str] = []
        tool_summaries: list[str] = []

        async for event in self.agent_loop.run(
            session_id=sub_session_id,
            user_message=prompt,
            model="auto",
        ):
            if isinstance(event, TextChunk):
                text_parts.append(event.content)
            elif isinstance(event, ToolCallResult):
                # Summarise tool output (truncate)
                summary = f"[{event.name}] {str(event.result)[:200]}"
                tool_summaries.append(summary)
            elif isinstance(event, RunError):
                logger.warning(f"research sub-session error: {event.error}")
            elif isinstance(event, RunComplete):
                pass

        output_parts = tool_summaries + text_parts
        output = "\n".join(output_parts).strip() or "(no output)"
        approach = "AgentLoop sub-session with tools"
        return approach, output

    async def _execute_via_llm(self, hypothesis: str) -> tuple[str, str]:
        """Fallback: direct LLM stream without tool execution."""
        from claw.llm.router_client import CompletionRequest, ChatMessage
        prompt = (
            f"Analyze this research hypothesis and report findings:\n\n"
            f"Hypothesis: {hypothesis}\n\n"
            f"Be concise and factual."
        )
        req = CompletionRequest(
            messages=[ChatMessage(role="user", content=prompt)],
            model="auto",
            max_tokens=512,
        )
        buf = ""
        async for chunk in self.llm.stream(req):
            if chunk.content:
                buf += chunk.content
        return "direct-llm", buf.strip()

    async def _run_eval_cmd(self, eval_cmd: str) -> float | None:
        """Run eval_cmd. Returns float from stdout or 0.0/1.0 from exit code."""
        proc = None
        try:
            proc = await asyncio.create_subprocess_shell(
                eval_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
            text = stdout.decode().strip()
            try:
                return float(text)
            except ValueError:
                return 0.0 if proc.returncode == 0 else 1.0
        except Exception as e:
            logger.warning(f"eval_cmd failed: {e}")
            return None
        finally:
            if proc is not None and proc.returncode is None:
                try:
                    proc.kill()
                    await asyncio.wait_for(proc.wait(), timeout=3)
                except Exception:
                    pass

    async def _evaluate(
        self,
        output: str,
        metric: float | None,
        criteria: str | None,
        eval_cmd: str | None,
        history: list[ExperimentResult],
    ) -> tuple[ExperimentStatus, str]:
        """Three-layer termination evaluation: A → C → B."""
        # A: explicit criteria
        if criteria:
            verdict = await self._ask_llm_bool(
                f"Does this result satisfy the success criteria?\n"
                f"Criteria: {criteria}\n"
                f"Result: {output[:600]}"
            )
            return (
                ExperimentStatus.KEEP if verdict else ExperimentStatus.DISCARD,
                f"A-layer: criteria {'met' if verdict else 'not met'}",
            )

        # C: quantitative metric
        if eval_cmd and metric is not None:
            kept = [r for r in history if r.status == ExperimentStatus.KEEP and r.metric is not None]
            best = min((r.metric for r in kept), default=float("inf"))
            if metric < best:
                return ExperimentStatus.KEEP, f"C-layer: metric improved {metric:.4f} < {best:.4f}"
            return ExperimentStatus.DISCARD, f"C-layer: no improvement {metric:.4f} >= {best:.4f}"

        # B: LLM self-evaluation
        verdict = await self._ask_llm_bool(
            f"Is this a useful finding for the research?\n"
            f"Result: {output[:600]}"
        )
        return (
            ExperimentStatus.KEEP if verdict else ExperimentStatus.DISCARD,
            f"B-layer: llm {'approved' if verdict else 'rejected'}",
        )

    async def _should_terminate(
        self,
        latest: ExperimentResult,
        criteria: str | None,
        eval_cmd: str | None,
        history: list[ExperimentResult],
    ) -> tuple[bool, str]:
        """Decide whether to stop the loop after a KEEP result."""
        if criteria:
            # A-layer already confirmed criteria met
            return True, "success criteria satisfied"
        if eval_cmd and latest.metric is not None and latest.metric == 0.0:
            return True, "eval_cmd returned 0 (success)"
        # B-layer: check if LLM thinks research is complete
        kept = [r for r in history if r.status == ExperimentStatus.KEEP]
        if len(kept) >= 3:
            verdict = await self._ask_llm_bool(
                f"Given {len(kept)} successful findings, is the research complete?"
            )
            if verdict:
                return True, "B-layer: sufficient findings accumulated"
        return False, ""

    async def _ask_llm_bool(self, question: str) -> bool:
        from claw.llm.router_client import CompletionRequest, ChatMessage
        req = CompletionRequest(
            messages=[
                ChatMessage(
                    role="system",
                    content="Answer ONLY with 'yes' or 'no'. Nothing else.",
                ),
                ChatMessage(role="user", content=question),
            ],
            model="auto",
            max_tokens=8,
        )
        buf = ""
        async for chunk in self.llm.stream(req):
            if chunk.content:
                buf += chunk.content
        return "yes" in buf.lower()


# Module-level singleton
_loop: ResearchLoop | None = None


def get_research_loop() -> ResearchLoop | None:
    return _loop


def set_research_loop(loop: ResearchLoop) -> None:
    global _loop
    _loop = loop


def init_research_loop(llm, storage=None, egress=None, memory=None) -> ResearchLoop:
    """
    Convenience factory: builds AgentLoop internally so ResearchLoop can use tools.
    Call this from main.py instead of constructing manually.
    """
    from claw.agent.loop import AgentLoop
    from claw.research.ledger import ResearchLedger

    agent_loop = None
    if storage is not None:
        agent_loop = AgentLoop(storage=storage, llm=llm, egress=egress, memory=memory)

    loop = ResearchLoop(llm=llm, agent_loop=agent_loop)
    set_research_loop(loop)
    return loop
