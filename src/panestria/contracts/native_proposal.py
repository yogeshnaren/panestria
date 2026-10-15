"""One deliberately small public synthetic task, not a general native worker."""

from __future__ import annotations

import ast
import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PROFILE = "claude-public-proposal-v1"
BASE_SOURCE = "def add(a, b):\n    return a - b\n"
TASK = (
    "Fix the public synthetic calculator.py function add(a, b) "
    "so it returns the sum for positive, negative and zero inputs."
)
PROMPT = (
    "You are proposing a candidate for a synthetic Panestria demo. You have no tools. "
    "Return ONLY a JSON object with exactly path and content. path must be calculator.py. "
    "content must contain only a Python function add(a, b), no imports, decorators or side effects. "
    "The controller will apply the candidate and independently test it. Do not claim verification or approval.\n"
    + TASK
    + "\nUntrusted source data follows:\n<source>\n"
    + BASE_SOURCE
    + "</source>\n"
)
PROMPT_SHA256 = hashlib.sha256(PROMPT.encode()).hexdigest()


class CodeProposal(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    path: Literal["calculator.py"]
    content: str = Field(min_length=1, max_length=4096)

    @field_validator("content")
    @classmethod
    def bounded_function(cls, value: str) -> str:
        try:
            if len(value.encode()) > 4096 or "\x00" in value:
                raise ValueError
            tree = ast.parse(value)
            if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
                raise ValueError
            fn = tree.body[0]
            if (
                fn.name != "add"
                or fn.decorator_list
                or [arg.arg for arg in fn.args.args] != ["a", "b"]
                or fn.args.posonlyargs
                or fn.args.kwonlyargs
                or fn.args.vararg
                or fn.args.kwarg
                or fn.args.defaults
            ):
                raise ValueError
            allowed = (
                ast.Module,
                ast.FunctionDef,
                ast.arguments,
                ast.arg,
                ast.Return,
                ast.BinOp,
                ast.Add,
                ast.Sub,
                ast.Mult,
                ast.Name,
                ast.Load,
                ast.Constant,
                ast.Expr,
            )
            if any(not isinstance(node, allowed) for node in ast.walk(tree)):
                raise ValueError
            if fn.returns is not None or any(arg.annotation is not None for arg in fn.args.args):
                raise ValueError
        except (ValueError, SyntaxError, UnicodeError, RecursionError):
            raise ValueError("invalid_demo_candidate") from None
        return value if value.endswith("\n") else value + "\n"
