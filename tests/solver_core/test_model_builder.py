from __future__ import annotations

from opmed.schemas.models import Config, Surgery
from opmed.solver_core.model_builder import CpSatModelBundle, ModelBuilder


def test_modelbuilder_stub_instantiation() -> None:
    """Ensure ModelBuilder can be instantiated and build() returns a valid bundle."""
    # Minimal config and synthetic surgeries
    cfg = Config()
    surgeries = [
        Surgery(
            surgery_id="s1",
            start_time="2025-01-01T08:00:00Z",
            end_time="2025-01-01T09:00:00Z",
        ),
        Surgery(
            surgery_id="s2",
            start_time="2025-01-01T09:30:00Z",
            end_time="2025-01-01T10:30:00Z",
        ),
    ]

    builder = ModelBuilder(cfg=cfg, surgeries=surgeries)
    bundle: CpSatModelBundle = builder.build()

    assert isinstance(bundle, dict)
    for key in ("model", "vars", "aux"):
        assert key in bundle
