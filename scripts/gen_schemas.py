# scripts/gen_schemas.py
"""
Generate JSON Schemas for Opmed data models.

This script exports JSON Schema files for:
    - Surgery
    - Config
    - SolutionRow

Output directory: schemas/
"""

import json
from pathlib import Path

from opmed.schemas.models import Config, SolutionRow, Surgery


def export_schema(model_cls, name: str, out_dir: Path) -> None:
    """
    @brief
    Exports the JSON schema of a given Pydantic model.

    @details
    Creates a JSON Schema file describing the structure of the provided data model.
    The schema is written into the specified output directory, ensuring directory
    existence and UTF-8 encoding. The result is printed relative to the current
    working directory for readability.

    @params
        model_cls : Type[BaseModel]
            The Pydantic model class whose schema will be generated.
        name : str
            Base name of the output file (without extension).
        out_dir : Path
            Target directory where the schema file will be written.

    @returns
        None. Writes a "<name>.schema.json" file to disk.

    @raises
        OSError
            If the schema file cannot be written.
    """
    # (1) Ensure output directory exists
    out_dir.mkdir(parents=True, exist_ok=True)

    # (2) Compute target path and generate schema data
    schema_path = (out_dir / f"{name}.schema.json").resolve()
    schema = model_cls.model_json_schema()

    # (3) Serialize JSON Schema to file with indentation and final newline
    with schema_path.open("w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # (4) Print confirmation with relative path for user feedback
    try:
        rel = schema_path.relative_to(Path.cwd())
    except ValueError:
        rel = schema_path
    print(f"✅  Generated {rel}")


def main() -> None:
    """
    @brief
    Entry point for JSON Schema generation.

    @details
    Invokes schema export for core Opmed models — Surgery, Config, and SolutionRow.
    All schema files are written into the `schemas/` directory at the repository root.
    """
    # (1) Define output directory
    out_dir = Path("schemas").resolve()

    # (2) Generate schemas for key data models
    export_schema(Surgery, "surgery", out_dir)
    export_schema(Config, "config", out_dir)
    export_schema(SolutionRow, "solution", out_dir)


if __name__ == "__main__":
    main()
