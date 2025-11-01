# src/opmed/errors.py
from __future__ import annotations

from datetime import datetime


class OpmedError(Exception):
    """Base class for all structured Opmed exceptions."""

    def __init__(
        self, message: str, source: str | None = None, suggested_action: str | None = None
    ):
        super().__init__(message)
        self.timestamp = datetime.utcnow().isoformat()
        self.error_type = self.__class__.__name__
        self.source = source or "unknown"
        self.suggested_action = suggested_action

    def __str__(self) -> str:
        base = f"[{self.error_type}] {self.args[0]}"
        if self.source:
            base += f" (source={self.source})"
        if self.suggested_action:
            base += f" | action: {self.suggested_action}"
        return base


class ConfigError(OpmedError):
    """Invalid or missing configuration (config.yaml)"""


class DataError(OpmedError):
    """Malformed or inconsistent input data"""


class ModelError(OpmedError):
    """Issues while building CP-SAT model"""


class SolveError(OpmedError):
    """Solver returned infeasible result or timeout"""


class ValidationError(OpmedError):
    """Failed schedule validation"""


class VisualizationError(OpmedError):
    """Plotting or rendering failure"""
