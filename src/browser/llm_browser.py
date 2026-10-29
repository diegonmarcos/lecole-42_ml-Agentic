"""
LLM-Driven Browser - Autonomous navigation using LLM reasoning

Features (TASK-017):
- LLM-driven element selection
- Natural language instructions
- Multi-step workflows
- LLM-as-judge validation (TASK-018)

Based on browser-use architecture (3-5x faster than manual automation).
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.providers.router import ProviderRouter, Tier, build_local_router

from .stealth_browser import BrowserConfig, StealthBrowser

logger = logging.getLogger(__name__)


@dataclass
class BrowserAction:
    """Browser action to perform"""

    action_type: str  # navigate, click, fill, wait, extract
    selector: Optional[str] = None
    value: Optional[str] = None
    url: Optional[str] = None
    reasoning: Optional[str] = None


@dataclass
class WorkflowResult:
    """Result of workflow execution"""

    success: bool
    steps_completed: int
    extracted_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    validation_score: Optional[float] = None


class LLMBrowser:
    """
    LLM-driven browser automation with intelligent navigation.

    Usage:
        browser = LLMBrowser(provider_router, tier=Tier.LOCAL_FREE)

        await browser.start()

        # Execute natural language task
        result = await browser.execute_task(
            "Go to example.com and find the contact email"
        )

        print(f"Success: {result.success}")
        print(f"Data: {result.extracted_data}")

        await browser.close()
    """

    def __init__(
        self,
        provider_router: ProviderRouter,
        tier: Tier = Tier.CLOUD_CHEAP,
        model: Optional[str] = None,
        browser_config: Optional[BrowserConfig] = None,
    ):
        """
        Initialize LLM-driven browser.

        Args:
            provider_router: LLM provider router
            tier: LLM tier to use for navigation
            model: Specific model (None = auto-select)
            browser_config: Browser configuration
        """
        self.router = provider_router
        self.tier = tier
        self.model = model or self._get_default_model(tier)
        self.browser = StealthBrowser(browser_config or BrowserConfig())

    def _get_default_model(self, tier: Tier) -> str:
        """Get default model for tier"""
        if tier == Tier.LOCAL_FREE:
            return "llama3.1:8b"
        if tier == Tier.CLOUD_CHEAP:
            return "meta-llama/Llama-3.1-8B-Instruct-Turbo"
        return "claude-3-5-haiku-20241022"

    async def start(self):
        """Start browser"""
        await self.browser.start()

    async def execute_task(
        self, instruction: str, max_steps: int = 10, validate: bool = True
    ) -> WorkflowResult:
        """
        Execute natural language task using LLM reasoning.

        Args:
            instruction: Natural language instruction
            max_steps: Maximum steps to execute
            validate: Whether to validate result with LLM-as-judge

        Returns:
            WorkflowResult with success status and extracted data
        """
        logger.info("Executing task: %s", instruction)

        steps_completed = 0
        extracted_data = {}
        error = None

        try:
            # Plan workflow
            actions = await self._plan_workflow(instruction)

            # Execute actions
            for i, action in enumerate(actions[:max_steps]):
                logger.info(
                    "Step %s/%s: %s - %s",
                    i + 1,
                    len(actions),
                    action.action_type,
                    action.reasoning,
                )

                success = await self._execute_action(action)

                if not success:
                    error = f"Failed at step {i+1}: {action.action_type}"
                    break

                steps_completed += 1

                # Extract data if requested
                if action.action_type == "extract":
                    page_content = await self.browser.get_page_text()
                    extracted_data = await self._extract_data(instruction, page_content)

            # Validate result
            validation_score = None
            if validate and steps_completed > 0:
                validation_score = await self._validate_result(
                    instruction, extracted_data, await self.browser.get_page_text()
                )

            success = error is None and steps_completed > 0

            return WorkflowResult(
                success=success,
                steps_completed=steps_completed,
                extracted_data=extracted_data if extracted_data else None,
                error=error,
                validation_score=validation_score,
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Task execution failed: %s", e)
            return WorkflowResult(
                success=False, steps_completed=steps_completed, error=str(e)
            )

    async def _plan_workflow(self, instruction: str) -> List[BrowserAction]:
        """
        Use LLM to plan workflow steps.

        Args:
            instruction: Natural language instruction

        Returns:
            List of browser actions to execute
        """
        prompt = f"""You are a browser automation planner. Given a user instruction, \
break it down into specific browser actions.

Available actions:
- navigate: Go to a URL
- click: Click an element (requires selector)
- fill: Fill a form field (requires selector and value)
- wait: Wait for an element to appear (requires selector)
- extract: Extract data from the page

User instruction: {instruction}

Respond with a JSON array of actions. Example:
[
  {{"action_type": "navigate", "url": "https://example.com", \
"reasoning": "Go to the target website"}},
  {{"action_type": "wait", "selector": "#content", "reasoning": "Wait for content to load"}},
  {{"action_type": "extract", "reasoning": "Extract the contact email from the page"}}
]

Actions:"""

        response = await self.router.chat_completion(
            tier=self.tier,
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1000,
        )

        # Parse JSON response
        try:
            actions_data = json.loads(response.content.strip())
            actions = [BrowserAction(**action) for action in actions_data]
            logger.info("Planned %s actions", len(actions))
            return actions
        except json.JSONDecodeError:
            logger.error("Failed to parse LLM response as JSON")
            # Fallback: simple navigate + extract
            return [
                BrowserAction(
                    action_type="extract", reasoning="Extract data from current page"
                )
            ]

    async def _execute_action(  # pylint: disable=too-many-return-statements
        self, action: BrowserAction
    ) -> bool:
        """
        Execute a single browser action.

        Args:
            action: Action to execute

        Returns:
            True if successful
        """
        try:
            if action.action_type == "navigate":
                if not action.url:
                    return False
                result = await self.browser.navigate(action.url)
                return result.success

            if action.action_type == "click":
                if not action.selector:
                    return False
                return await self.browser.click(action.selector)

            if action.action_type == "fill":
                if not action.selector or action.value is None:
                    return False
                return await self.browser.fill(action.selector, action.value)

            if action.action_type == "wait":
                if not action.selector:
                    return False
                return await self.browser.wait_for_selector(action.selector)

            if action.action_type == "extract":
                # Data extraction handled in execute_task
                return True

            logger.warning("Unknown action type: %s", action.action_type)
            return False

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Action execution failed: %s", e)
            return False

    async def _extract_data(
        self, instruction: str, page_content: str
    ) -> Dict[str, Any]:
        """
        Extract data from page using LLM.

        Args:
            instruction: Original instruction
            page_content: Page text content

        Returns:
            Extracted data dictionary
        """
        # Truncate content if too long
        max_content_length = 4000
        if len(page_content) > max_content_length:
            page_content = page_content[:max_content_length] + "...(truncated)"

        prompt = f"""Extract relevant information from the page based on the user's request.

User request: {instruction}

Page content:
{page_content}

Respond with JSON containing the extracted data. Example:
{{
  "email": "contact@example.com",
  "phone": "+1-555-0123"
}}

Extracted data:"""

        response = await self.router.chat_completion(
            tier=self.tier,
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500,
        )

        # Parse JSON response
        try:
            data = json.loads(response.content.strip())
            logger.info("Extracted data: %s", data)
            return data
        except json.JSONDecodeError:
            logger.error("Failed to parse extraction result")
            return {"raw_response": response.content}

    async def _validate_result(
        self,
        instruction: str,
        extracted_data: Optional[Dict[str, Any]],
        page_content: str,
    ) -> float:
        """
        Validate result using LLM-as-judge (TASK-018).

        Args:
            instruction: Original instruction
            extracted_data: Extracted data
            page_content: Page content

        Returns:
            Validation score (0-1, higher = better)
        """
        # Truncate content
        max_content_length = 2000
        if len(page_content) > max_content_length:
            page_content = page_content[:max_content_length] + "...(truncated)"

        prompt = f"""You are a quality judge for browser automation tasks. \
Evaluate whether the task was completed successfully.

User instruction: {instruction}

Extracted data: {json.dumps(extracted_data, indent=2)}

Page content:
{page_content}

Evaluate on a scale of 0-10:
- 10: Task completed perfectly, data is accurate and complete
- 7-9: Task mostly completed, data is mostly accurate
- 4-6: Task partially completed, some data missing or incorrect
- 1-3: Task barely completed, most data missing or incorrect
- 0: Task failed completely

Respond with ONLY a single number from 0-10.

Score:"""

        response = await self.router.chat_completion(
            tier=Tier.PREMIUM,  # Use premium LLM for validation
            model="claude-3-5-haiku-20241022",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=10,
        )

        # Parse score
        try:
            score = float(response.content.strip())
            # Normalize to 0-1
            normalized_score = score / 10.0
            logger.info("Validation score: %.2f", normalized_score)
            return normalized_score
        except ValueError:
            logger.error("Failed to parse validation score: %s", response.content)
            return 0.5  # Neutral score

    async def get_page_summary(self) -> str:
        """
        Get LLM-generated summary of current page.

        Returns:
            Page summary
        """
        page_content = await self.browser.get_page_text()

        # Truncate
        max_length = 3000
        if len(page_content) > max_length:
            page_content = page_content[:max_length] + "...(truncated)"

        prompt = f"""Summarize the following web page content in 2-3 sentences:

{page_content}

Summary:"""

        response = await self.router.chat_completion(
            tier=self.tier,
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=200,
        )

        return response.content.strip()

    async def close(self):
        """Close browser"""
        await self.browser.close()


# Example usage
if __name__ == "__main__":

    async def main():
        # Create provider router
        router = build_local_router()

        # Create LLM browser
        browser = LLMBrowser(router, tier=Tier.LOCAL_FREE)

        try:
            await browser.start()

            # Execute task
            result = await browser.execute_task(
                "Go to example.com and summarize the main heading",
                max_steps=5,
                validate=True,
            )

            print("\nTask result:")
            print(f"Success: {result.success}")
            print(f"Steps: {result.steps_completed}")
            print(f"Data: {result.extracted_data}")
            print(
                f"Validation: {result.validation_score:.2f}"
                if result.validation_score
                else "No validation"
            )

        finally:
            await browser.close()

    asyncio.run(main())
