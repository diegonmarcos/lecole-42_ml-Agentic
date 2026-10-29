"""
Code Workbench - Specialized tools for code analysis and manipulation

Provides agents with code-related capabilities:
- Code search and analysis
- AST parsing and manipulation
- Syntax checking
- Dependency analysis
- Code generation assistance

Based on patterns from AutoGen and Flowise.
"""

import ast
import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..registry import ToolRegistry, get_registry

logger = logging.getLogger(__name__)


class CodeWorkbench:
    """
    Code analysis and manipulation workbench.

    Registers code-related tools with the global registry.
    """

    def __init__(self, registry: Optional[ToolRegistry] = None):
        """
        Initialize code workbench.

        Args:
            registry: Tool registry (uses global if None)
        """
        self.registry = registry or get_registry()
        self._register_tools()

    def _register_tools(self):  # pylint: disable=too-many-statements
        """Register all code tools"""

        @self.registry.register_function(
            description="Search for code patterns using regex", category="code"
        )
        async def code_search(
            pattern: str,
            directory: str,
            file_extension: str = ".py",
            max_results: int = 50,
        ) -> List[Dict[str, Any]]:
            """Search for code patterns in files"""
            results = []
            pattern_re = re.compile(pattern)

            for root, dirs, files in os.walk(directory):
                # Skip common ignore directories
                dirs[:] = [
                    d
                    for d in dirs
                    if d not in {".git", "__pycache__", "node_modules", ".venv", "venv"}
                ]

                for file in files:
                    if not file.endswith(file_extension):
                        continue

                    filepath = Path(root) / file
                    try:
                        content = filepath.read_text(encoding="utf-8")
                        matches = pattern_re.finditer(content)

                        for match in matches:
                            line_no = content[: match.start()].count("\n") + 1
                            results.append(
                                {
                                    "file": str(filepath),
                                    "line": line_no,
                                    "match": match.group(),
                                    "context": content.split("\n")[line_no - 1].strip(),
                                }
                            )

                            if len(results) >= max_results:
                                return results

                    except Exception as e:  # pylint: disable=broad-exception-caught
                        logger.debug("Error reading %s: %s", filepath, e)
                        continue

            return results

        @self.registry.register_function(
            description="Parse Python code and extract structure (classes, functions, imports)",
            category="code",
        )
        async def parse_python(code: str) -> Dict[str, Any]:
            """Parse Python code and extract structure"""
            try:
                tree = ast.parse(code)

                classes = []
                functions = []
                imports = []

                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        methods = [
                            m.name for m in node.body if isinstance(m, ast.FunctionDef)
                        ]
                        classes.append(
                            {
                                "name": node.name,
                                "line": node.lineno,
                                "methods": methods,
                                "bases": [ast.unparse(base) for base in node.bases],
                            }
                        )

                    elif isinstance(node, ast.FunctionDef):
                        # Only top-level functions (not methods)
                        if not any(
                            isinstance(parent, ast.ClassDef)
                            for parent in ast.walk(tree)
                        ):
                            params = [arg.arg for arg in node.args.args]
                            functions.append(
                                {
                                    "name": node.name,
                                    "line": node.lineno,
                                    "parameters": params,
                                    "is_async": isinstance(node, ast.AsyncFunctionDef),
                                }
                            )

                    elif isinstance(node, (ast.Import, ast.ImportFrom)):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                imports.append(
                                    {
                                        "module": alias.name,
                                        "alias": alias.asname,
                                        "line": node.lineno,
                                    }
                                )
                        else:
                            module = node.module or ""
                            for alias in node.names:
                                imports.append(
                                    {
                                        "module": f"{module}.{alias.name}",
                                        "alias": alias.asname,
                                        "line": node.lineno,
                                    }
                                )

                return {
                    "success": True,
                    "classes": classes,
                    "functions": functions,
                    "imports": imports,
                    "total_lines": len(code.split("\n")),
                }

            except SyntaxError as e:
                return {"success": False, "error": str(e), "line": e.lineno}

        @self.registry.register_function(
            description="Check Python code syntax without executing", category="code"
        )
        async def check_syntax(code: str) -> Dict[str, Any]:
            """Check Python code syntax"""
            try:
                compile(code, "<string>", "exec")
                return {"valid": True, "message": "Syntax is valid"}
            except SyntaxError as e:
                return {
                    "valid": False,
                    "error": str(e),
                    "line": e.lineno,
                    "offset": e.offset,
                    "text": e.text,
                }

        @self.registry.register_function(
            description="Extract function signature and docstring", category="code"
        )
        async def get_function_info(
            code: str, function_name: str
        ) -> Optional[Dict[str, Any]]:
            """Extract function information"""
            try:
                tree = ast.parse(code)

                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and node.name == function_name:
                        # Extract parameters
                        params = []
                        for arg in node.args.args:
                            param_info = {"name": arg.arg}

                            # Type annotation
                            if arg.annotation:
                                param_info["type"] = ast.unparse(arg.annotation)

                            params.append(param_info)

                        # Extract docstring
                        docstring = ast.get_docstring(node)

                        # Return type
                        return_type = None
                        if node.returns:
                            return_type = ast.unparse(node.returns)

                        return {
                            "name": function_name,
                            "line": node.lineno,
                            "parameters": params,
                            "return_type": return_type,
                            "docstring": docstring,
                            "is_async": isinstance(node, ast.AsyncFunctionDef),
                            "decorator_list": [
                                ast.unparse(d) for d in node.decorator_list
                            ],
                        }

                return None

            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("Error extracting function info: %s", e)
                return None

        @self.registry.register_function(
            description="Find dependencies (imports) in Python code", category="code"
        )
        async def find_dependencies(code: str) -> List[str]:
            """Find all dependencies in Python code"""
            try:
                tree = ast.parse(code)
                dependencies = set()

                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            # Get base package name
                            base = alias.name.split(".")[0]
                            dependencies.add(base)

                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            base = node.module.split(".")[0]
                            dependencies.add(base)

                return sorted(list(dependencies))

            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("Error finding dependencies: %s", e)
                return []

        @self.registry.register_function(
            description="Count lines of code (excluding comments and blank lines)",
            category="code",
        )
        async def count_loc(code: str) -> Dict[str, int]:
            """Count lines of code"""
            lines = code.split("\n")

            total = len(lines)
            blank = sum(1 for line in lines if not line.strip())
            comments = sum(1 for line in lines if line.strip().startswith("#"))
            code_lines = total - blank - comments

            return {
                "total": total,
                "code": code_lines,
                "blank": blank,
                "comments": comments,
            }

        @self.registry.register_function(
            description="Format Python code using black (if available)",
            category="code",
            timeout=10,
        )
        async def format_code(code: str) -> Dict[str, Any]:
            """Format Python code"""
            try:
                # Try to use black if available
                proc = await asyncio.create_subprocess_exec(
                    "black",
                    "-",
                    "--quiet",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout, _ = await proc.communicate(code.encode())

                if proc.returncode == 0:
                    return {
                        "success": True,
                        "formatted_code": stdout.decode(),
                        "formatter": "black",
                    }
                # Fallback: basic formatting
                return {
                    "success": False,
                    "error": "black not available",
                    "formatted_code": code,
                }

            except FileNotFoundError:
                # Black not installed
                return {
                    "success": False,
                    "error": "black not installed",
                    "formatted_code": code,
                }

        @self.registry.register_function(
            description="Extract all TODO/FIXME/NOTE comments from code",
            category="code",
        )
        async def extract_todos(code: str) -> List[Dict[str, Any]]:
            """Extract TODO comments"""
            lines = code.split("\n")
            todos = []

            markers = ["TODO", "FIXME", "NOTE", "HACK", "XXX"]

            for i, line in enumerate(lines, 1):
                for marker in markers:
                    if marker in line and "#" in line:
                        # Extract comment
                        comment = line[line.index("#") :].strip("# ")

                        todos.append(
                            {
                                "line": i,
                                "type": marker,
                                "text": comment,
                                "context": line.strip(),
                            }
                        )
                        break

            return todos

        @self.registry.register_function(
            description="Calculate cyclomatic complexity of Python code",
            category="code",
        )
        async def calculate_complexity(code: str) -> Dict[str, Any]:
            """Calculate code complexity"""
            try:
                tree = ast.parse(code)
                complexity_scores = {}

                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        # Count decision points
                        complexity = 1  # Base complexity

                        for child in ast.walk(node):
                            # Add complexity for control flow
                            if isinstance(
                                child, (ast.If, ast.While, ast.For, ast.ExceptHandler)
                            ):
                                complexity += 1
                            elif isinstance(child, ast.BoolOp):
                                # Each boolean operator adds complexity
                                complexity += len(child.values) - 1

                        complexity_scores[node.name] = complexity

                avg_complexity = (
                    sum(complexity_scores.values()) / len(complexity_scores)
                    if complexity_scores
                    else 0
                )

                return {
                    "functions": complexity_scores,
                    "average": round(avg_complexity, 2),
                    "max": max(complexity_scores.values()) if complexity_scores else 0,
                    "total_functions": len(complexity_scores),
                }

            except Exception as e:  # pylint: disable=broad-exception-caught
                return {"error": str(e)}

        logger.info(
            "Registered %s code tools",
            len(list(self.registry.list_tools(category="code"))),
        )


# Example usage
if __name__ == "__main__":

    async def main():
        registry = ToolRegistry()
        CodeWorkbench(registry)

        # Example: Parse Python code
        sample_code = '''
import asyncio
from typing import List

class DataProcessor:
    """Process data efficiently"""

    def __init__(self, name: str):
        self.name = name

    async def process(self, data: List[int]) -> int:
        """Process data and return sum"""
        # TODO: Add validation
        return sum(data)

async def main():
    processor = DataProcessor("test")
    result = await processor.process([1, 2, 3])
    print(result)
'''

        # Parse code
        result = await registry.execute("parse_python", {"code": sample_code})
        print("Parsed structure:")
        print(f"  Classes: {result.output['classes']}")
        print(f"  Functions: {result.output['functions']}")
        print(f"  Imports: {result.output['imports']}")

        # Count LOC
        loc = await registry.execute("count_loc", {"code": sample_code})
        print(f"\nLines of code: {loc.output}")

        # Extract TODOs
        todos = await registry.execute("extract_todos", {"code": sample_code})
        print(f"\nTODOs found: {len(todos.output)}")
        for todo in todos.output:
            print(f"  Line {todo['line']}: {todo['text']}")

        # Calculate complexity
        complexity = await registry.execute(
            "calculate_complexity", {"code": sample_code}
        )
        print(f"\nComplexity: {complexity.output}")

    asyncio.run(main())
