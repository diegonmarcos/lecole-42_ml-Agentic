"""
Coder Agent - Code generation and modification

Uses Tier 1 LLM for cost-effective code generation.
Accesses code workbench tools.
"""

import json
import logging
from typing import Any, Dict

from src.providers.router import Tier

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class CoderAgent(BaseAgent):
    """
    Coder agent for code generation and modification.

    Uses Tier 1 LLM for efficient code generation.
    """

    def __init__(self, *args, **kwargs):
        """Initialize coder agent"""
        # Use Tier 1 for cost efficiency
        kwargs["tier"] = kwargs.get("tier", Tier.CLOUD_CHEAP)
        kwargs["model"] = kwargs.get("model", "meta-llama/Llama-3.1-70B-Instruct-Turbo")

        super().__init__(*args, **kwargs)

    async def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process coding task.

        Args:
            task: Task dict with 'instruction' and optional 'context'

        Returns:
            Generated code and analysis
        """
        instruction = task.get("instruction", "")
        context = task.get("context", "")

        if not instruction:
            return {"error": "No instruction provided"}

        logger.info("Coding task: %s", instruction)

        # Build prompt
        code_prompt = f"""Generate code for the following task:

Task: {instruction}

{f"Context: {context}" if context else ""}

Requirements:
1. Write clean, well-documented code
2. Include type hints
3. Add error handling
4. Follow PEP 8 style guidelines
5. Include docstrings

Respond with JSON:
{{
  "code": "Generated code here",
  "explanation": "Brief explanation of the implementation",
  "dependencies": ["List of required packages"],
  "test_cases": ["Example test cases"]
}}

Response:"""

        response = await self.call_llm(
            messages=[{"role": "user", "content": code_prompt}],
            temperature=0.2,
            max_tokens=2000,
        )

        # Parse response
        try:
            result = json.loads(response)

            # Validate syntax if code is Python
            if "code" in result:
                syntax_check = await self.use_tool(
                    "check_syntax", {"code": result["code"]}
                )

                result["syntax_valid"] = (
                    syntax_check.get("valid", False) if syntax_check else False
                )

            # Remember generated code
            self.remember("last_code", result.get("code"))

            return {"status": "success", "result": result, "coder": self.agent_id}

        except json.JSONDecodeError:
            logger.warning("Non-JSON response, returning raw code")

            # Fallback: treat as raw code
            return {
                "status": "success",
                "result": {
                    "code": response,
                    "explanation": "Generated code (raw format)",
                },
                "coder": self.agent_id,
            }

    def get_system_prompt(self) -> str:
        """Get coder system prompt"""
        return """You are an expert software engineer specializing in Python development.

Your role:
1. Generate clean, efficient, and maintainable code
2. Write comprehensive documentation and docstrings
3. Implement proper error handling
4. Follow best practices and style guidelines
5. Consider edge cases and performance

Guidelines:
- Always use type hints
- Write self-documenting code
- Include helpful comments for complex logic
- Optimize for readability over cleverness
- Prefer async/await for I/O operations
- Output valid JSON when requested"""
