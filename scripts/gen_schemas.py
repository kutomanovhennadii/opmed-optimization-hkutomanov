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
    """Export a model's JSON schema to <out_dir>/<name>.schema.json"""
    out_dir.mkdir(parents=True, exist_ok=True)
    schema_path = (out_dir / f"{name}.schema.json").resolve()
    schema = model_cls.model_json_schema()

    with schema_path.open("w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)
        f.write("\n")  # гарантируем завершающую пустую строку

    try:
        rel = schema_path.relative_to(Path.cwd())
    except ValueError:
        rel = schema_path
    print(f"✅  Generated {rel}")


def main() -> None:
    out_dir = Path("schemas").resolve()
    export_schema(Surgery, "surgery", out_dir)
    export_schema(Config, "config", out_dir)
    export_schema(SolutionRow, "solution", out_dir)


if __name__ == "__main__":
    main()
