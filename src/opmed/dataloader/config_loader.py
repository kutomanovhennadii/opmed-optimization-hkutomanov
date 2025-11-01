# src/opmed/dataloader/config_loader.py
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from opmed.errors import ConfigError
from opmed.schemas.models import Config


class ConfigLoader:
    """
    @brief
    Loader responsible for reading and validating runtime configuration.

    @details
    Provides strict, single-responsibility handling of configuration files.
    Reads YAML from disk, parses it into a mapping, validates structure
    against the Pydantic `Config` schema, and raises structured `ConfigError`
    instances for all failure modes.
    """

    def load(self, path: Path) -> Config:
        """
        @brief
        Load and validate configuration from YAML file.

        @details
        Entry point for consumers. Reads YAML, parses content, and validates
        the resulting mapping via Pydantic schema to produce a fully validated
        `Config` object with defaults applied.

        @params
            path : Path
                Filesystem path to configuration file (.yaml or .yml).

        @returns
            Validated Config instance.

        @raises
            ConfigError
                Raised if file is missing, malformed, or fails schema validation.
        """
        # (1) Read and parse YAML configuration file
        data = self._read_yaml(path)

        # (2) Validate mapping against Pydantic schema
        return self._validate(data)

    def _read_yaml(self, path: Path) -> dict[str, Any]:
        """
        @brief
        Read YAML file into Python mapping with strict checks.

        @details
        Validates file existence, extension, readability, and syntax.
        Ensures non-empty content and top-level mapping structure before returning
        a normalized dictionary. Raises `ConfigError` for any structural or I/O problem.

        @params
            path : Path
                Path to the YAML configuration file.

        @returns
            Parsed configuration dictionary.

        @raises
            ConfigError
                Raised on invalid path type, missing file, wrong extension,
                I/O error, syntax error, empty file, or non-mapping structure.
        """
        # (1) Validate path type and existence
        if not isinstance(path, Path):
            raise ConfigError(
                message=f"Invalid path type: expected pathlib.Path, got {type(path).__name__}",
                source="ConfigLoader._read_yaml",
                suggested_action="Pass a pathlib.Path object pointing to config.yaml.",
            )

        if not path.exists():
            raise ConfigError(
                message=f"Configuration file not found: {path}",
                source="ConfigLoader._read_yaml",
                suggested_action="Ensure config.yaml exists and the path is correct.",
            )

        # (2) Enforce correct file extension
        if path.suffix.lower() not in {".yaml", ".yml"}:
            raise ConfigError(
                message=f"Invalid configuration file extension: {path.suffix}",
                source="ConfigLoader._read_yaml",
                suggested_action="Use .yaml or .yml extension for configuration files.",
            )

        # (3) Read and parse YAML content
        try:
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigError(
                message=f"YAML parsing failed: {e}",
                source="ConfigLoader._read_yaml",
                suggested_action="Fix YAML syntax/indentation. Validate with an online YAML linter.",
            ) from e
        except OSError as e:
            raise ConfigError(
                message=f"Unable to read configuration file: {e}",
                source="ConfigLoader._read_yaml",
                suggested_action="Check file permissions and path accessibility.",
            ) from e

        # (4) Validate structural integrity of parsed data
        if data is None:
            raise ConfigError(
                message="Configuration file is empty.",
                source="ConfigLoader._read_yaml",
                suggested_action="Populate config.yaml with required parameters.",
            )

        if not isinstance(data, Mapping):
            raise ConfigError(
                message="Configuration root must be a mapping (key: value pairs).",
                source="ConfigLoader._read_yaml",
                suggested_action="Ensure top-level YAML structure uses key: value mappings.",
            )

        # (5) Normalize mapping to plain dict[str, Any]
        return dict(data)

    def _validate(self, data: dict[str, Any]) -> Config:
        """
        @brief
        Validate parsed configuration mapping via Pydantic schema.

        @details
        Creates `Config` object using Pydantic validation. Wraps
        `ValidationError` in a structured `ConfigError` with contextual
        information about field mismatches, missing keys, or type violations.

        @params
            data : dict[str, Any]
                Parsed configuration mapping.

        @returns
            Validated Config object instance.

        @raises
            ConfigError
                Raised if schema validation fails due to structural inconsistencies.
        """
        # (1) Attempt schema validation via Pydantic
        try:
            return Config(**data)
        except ValidationError as e:
            # (2) Wrap Pydantic error in standardized ConfigError
            raise ConfigError(
                message=f"Invalid configuration structure: {e}",
                source="ConfigLoader._validate",
                suggested_action=(
                    "Check field names, types, and bounds in config.yaml. "
                    "Remove unknown keys (extra fields are forbidden)."
                ),
            ) from e


__all__ = ["ConfigLoader"]
