from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from claw.research.experiment import ExperimentResult

logger = logging.getLogger(__name__)

_DECOMPOSE_PROMPT = """You are a research planning assistant. Given a complex research question,
decompose it into 3-5 specific, independent, verifiable hypotheses or sub-approaches.

Each hypothesis must be:
- Concrete and actionable (can be tested in one experiment)
- Independent of the others
- Directly relevant to the research question

Return ONLY a numbered list, one hypothesis per line. No explanations."""

_NEXT_HYPOTHESIS_PROMPT = """You are guiding an autonomous research loop.

Research question: {question}

Completed experiments so far:
{history}

Generate the NEXT hypothesis to test. It must:
- Build on successful (KEEP) results if any exist
- Avoid repeating approaches that were discarded
- Be specific and immediately testable

Return ONLY the hypothesis, nothing else."""


class ResearchPlanner:
    """Generates and manages research hypotheses using the LLM."""

    def __init__(self, llm):
        self.llm = llm

    async def decompose(self, question: str) -> list[str]:
        """Break a complex question into initial hypotheses."""
        from claw.llm.router_client import CompletionRequest, ChatMessage
        req = CompletionRequest(
            messages=[
                ChatMessage(role="system", content=_DECOMPOSE_PROMPT),
                ChatMessage(role="user", content=f"Research question: {question}"),
            ],
            model="auto",
            max_tokens=512,
        )
        buf = ""
        async for chunk in self.llm.stream(req):
            if chunk.content:
                buf += chunk.content
        hypotheses = [
            line.lstrip("0123456789.-) ").strip()
            for line in buf.strip().splitlines()
            if line.strip() and line[0].isdigit()
        ]
        return hypotheses if hypotheses else [question]

    async def next_hypothesis(
        self,
        question: str,
        history: list[ExperimentResult],
    ) -> str:
        """Generate the next hypothesis based on history."""
        from claw.llm.router_client import CompletionRequest, ChatMessage

        history_text = "\n".join(
            f"- [{r.status.value.upper()}] {r.hypothesis}: {r.reasoning}"
            for r in history[-10:]  # last 10 experiments
        ) or "(no experiments yet)"

        prompt = _NEXT_HYPOTHESIS_PROMPT.format(
            question=question, history=history_text
        )
        req = CompletionRequest(
            messages=[ChatMessage(role="user", content=prompt)],
            model="auto",
            max_tokens=256,
        )
        buf = ""
        async for chunk in self.llm.stream(req):
            if chunk.content:
                buf += chunk.content
        return buf.strip() or question
