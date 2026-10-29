"""
Planner Agent - High-level task planning and decomposition

Uses Tier 3 LLM (Claude/GPT-4) for complex reasoning.
Breaks down complex tasks into actionable steps.
"""

import json
import logging
from typing import Any, Dict

from src.providers.router import Tier

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class PlannerAgent(BaseAgent):
    """
    Planner agent for task decomposition and planning.

    Uses premium LLM for high-quality planning.
    """

    def __init__(self, *args, **kwargs):
        """Initialize planner agent"""
        # Override tier to use premium LLM
        kwargs["tier"] = Tier.PREMIUM
        kwargs["model"] = kwargs.get("model", "claude-3-5-haiku-20241022")

        super().__init__(*args, **kwargs)

    async def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process planning task.

        Args:
            task: Task dict with 'instruction' key

        Returns:
            Plan with steps
        """
        instruction = task.get("instruction", "")

        if not instruction:
            return {"error": "No instruction provided"}

        logger.info("Planning task: %s", instruction)

        # Call LLM for planning
        plan_prompt = f"""Break down the following task into concrete, actionable steps:

Task: {instruction}

Respond with a JSON object containing:
{{
  "summary": "Brief summary of the plan",
  "steps": [
    {{
      "step_number": 1,
      "action": "Specific action to take",
      "agent": "Which agent should handle this (coder/reviewer/searcher)",
      "dependencies": []
    }}
  ],
  "estimated_time": "Estimated completion time"
}}

Plan:"""

        response = await self.call_llm(
            messages=[{"role": "user", "content": plan_prompt}],
            temperature=0.3,
            max_tokens=1000,
        )

        # Parse plan
        try:
            plan = json.loads(response)

            # Remember the plan
            self.remember("last_plan", plan)

            return {"status": "success", "plan": plan, "planner": self.agent_id}

        except json.JSONDecodeError:
            logger.error("Failed to parse plan: %s", response)
            return {
                "status": "error",
                "error": "Failed to parse plan",
                "raw_response": response,
            }

    def get_system_prompt(self) -> str:
        """Get planner system prompt"""
        return """You are an expert task planner and project manager.

Your role:
1. Analyze complex tasks and break them down into clear, actionable steps
2. Identify dependencies between steps
3. Assign steps to appropriate specialist agents (coder, reviewer, searcher)
4. Estimate time requirements
5. Ensure plans are comprehensive yet efficient

Guidelines:
- Be specific and concrete in step descriptions
- Consider edge cases and error handling
- Optimize for parallel execution where possible
- Keep steps focused and single-purpose
- Always output valid JSON format"""
