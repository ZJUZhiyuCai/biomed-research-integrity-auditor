from typing import Any

from .contracts import ContractError, validate_contract

__version__ = "0.1.0"

__all__ = [
    "AdapterProtocol",
    "CommandAdapter",
    "ContractError",
    "evaluate_benchmark",
    "run_benchmark",
    "validate_contract",
    "__version__",
]


def __getattr__(name: str) -> Any:
    if name in {"AdapterProtocol", "CommandAdapter", "evaluate_benchmark", "run_benchmark"}:
        from . import cli

        return getattr(cli, name)
    raise AttributeError(name)
