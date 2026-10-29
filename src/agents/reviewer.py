"""
Reviewer Agent - Code review and quality assurance

Uses Tier 3 LLM for thorough code review.
Analyzes code quality, security, and best practices.
"""

import json
import logging
from typing import Any, Dict

from src.providers.router import Tier

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class ReviewerAgent(BaseAgent):
    """
    Reviewer agent for code quality assurance.

    Uses premium LLM for comprehensive review.
    """

    def __init__(self, *args, **kwargs):
        """Initialize reviewer agent"""
        # Use premium LLM for quality review
        kwargs["tier"] = Tier.PREMIUM
        kwargs["model"] = kwargs.get("model", "claude-3-5-haiku-20241022")

        super().__init__(*args, **kwargs)

    async def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process code review task.

        Args:
            task: Task dict with 'code' to review

        Returns:
            Review results with suggestions
        """
        code = task.get("code", "")

        if not code:
            return {"error": "No code provided"}

        logger.info("Reviewing code (%s chars)", len(code))

        # Use code workbench tools for analysis
        parse_result = await self.use_tool("parse_python", {"code": code})
        complexity = await self.use_tool("calculate_complexity", {"code": code})
        todos = await self.use_tool("extract_todos", {"code": code})
        dependencies = await self.use_tool("find_dependencies", {"code": code})

        # Build review prompt
        review_prompt = f"""Review the following Python code for quality, security, and \
best practices:

Code:
```python
{code}
```

Analysis data:
- Structure: {json.dumps(parse_result, indent=2) if parse_result else 'N/A'}
- Complexity: {json.dumps(complexity, indent=2) if complexity else 'N/A'}
- TODOs: {len(todos) if todos else 0}
- Dependencies: {dependencies if dependencies else []}

Provide a comprehensive review with JSON format:
{{
  "overall_rating": "Excellent/Good/Fair/Poor",
  "score": 0-100,
  "strengths": ["List of strengths"],
  "issues": [
    {{
      "severity": "critical/major/minor",
      "category": "security/performance/style/documentation",
      "description": "Issue description",
      "line": 0,
      "suggestion": "How to fix"
    }}
  ],
  "suggestions": ["List of improvement suggestions"],
  "security_concerns": ["Any security issues"],
  "performance_notes": ["Performance considerations"],
  "approved": true/false
}}

Review:"""

        response = await self.call_llm(
            messages=[{"role": "user", "content": review_prompt}],
            temperature=0.1,
            max_tokens=1500,
        )

        # Parse review
        try:
            review = json.loads(response)

            # Remember review
            self.remember("last_review", review)

            return {
                "status": "success",
                "review": review,
                "analysis": {
                    "complexity": complexity,
                    "todo_count": len(todos) if todos else 0,
                    "dependencies": dependencies,
                },
                "reviewer": self.agent_id,
            }

        except json.JSONDecodeError:
            logger.error("Failed to parse review: %s", response)
            return {
                "status": "error",
                "error": "Failed to parse review",
                "raw_response": response,
            }

    def get_system_prompt(self) -> str:
        """Get reviewer system prompt"""
        return """You are an expert code reviewer with deep knowledge of software \
engineering best practices.

Your role:
1. Analyze code for correctness, efficiency, and maintainability
2. Identify security vulnerabilities and potential bugs
3. Check adherence to style guidelines and best practices
4. Provide constructive, actionable feedback
5. Rate code quality objectively

Review criteria:
- **Security**: SQL injection, XSS, command injection, secrets in code
- **Performance**: O(n) complexity, unnecessary loops, memory leaks
- **Style**: PEP 8, naming conventions, code organization
- **Documentation**: Docstrings, comments, type hints
- **Error handling**: Try-except blocks, validation, edge cases
- **Testing**: Testability, test coverage potential

Guidelines:
- Be thorough but constructive
- Prioritize issues by severity
- Provide specific line numbers when possible
- Suggest concrete improvements
- Always output valid JSON format"""
