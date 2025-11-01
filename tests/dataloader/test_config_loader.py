# tests/dataloader/test_config_loader.py

from pathlib import Path

import pytest
import yaml

from opmed.dataloader.config_loader import ConfigLoader
from opmed.errors import ConfigError
from opmed.schemas.models import Config


@pytest.fixture()
def tmp_yaml(tmp_path: Path) -> Path:
    """Создаёт временный YAML с корректными полями Config."""
    path = tmp_path / "config.yaml"
    cfg = {
        "time_unit": 0.0833,
        "rooms_max": 20,
        "shift_min": 5,
        "shift_max": 12,
        "solver": {"num_workers": 2},
    }
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f)
    return path


def test_load_valid_yaml_returns_config(tmp_yaml: Path):
    """
    @brief
    Verify that valid YAML is correctly parsed and validated.

    @details
    Ensures that a well-formed YAML configuration file produces
    a fully validated `Config` object. Confirms default values
    (timezone, solver.search_branching) are correctly applied.
    """
    # --- Arrange ---
    loader = ConfigLoader()

    # --- Act ---
    cfg = loader.load(tmp_yaml)

    # --- Assert ---
    assert isinstance(cfg, Config)
    assert cfg.rooms_max == 20
    assert cfg.shift_min == 5
    assert cfg.timezone == "UTC"
    assert cfg.solver.search_branching == "AUTOMATIC"


def test_missing_file_raises_configerror(tmp_path: Path):
    """
    @brief
    Missing configuration file triggers ConfigError.

    @details
    Simulates loading from a nonexistent file and checks that
    a descriptive `ConfigError` is raised with relevant message.
    """
    # --- Arrange ---
    loader = ConfigLoader()
    path = tmp_path / "no_such.yaml"

    # --- Act / Assert ---
    with pytest.raises(ConfigError) as e:
        loader.load(path)

    # --- Assert ---
    msg = str(e.value)
    assert "not found" in msg or "Configuration file not found" in msg


def test_wrong_extension_raises_configerror(tmp_path: Path):
    """
    @brief
    Invalid file extension results in ConfigError.

    @details
    Ensures that only `.yaml` or `.yml` files are accepted.
    """
    # --- Arrange ---
    path = tmp_path / "config.txt"
    path.write_text("rooms_max: 10", encoding="utf-8")
    loader = ConfigLoader()

    # --- Act / Assert ---
    with pytest.raises(ConfigError):
        loader.load(path)


def test_empty_yaml_raises_configerror(tmp_path: Path):
    """
    @brief
    Empty YAML file triggers ConfigError.

    @details
    Verifies detection of empty configuration files and
    proper error reporting.
    """
    # --- Arrange ---
    path = tmp_path / "config.yaml"
    path.write_text("", encoding="utf-8")
    loader = ConfigLoader()

    # --- Act / Assert ---
    with pytest.raises(ConfigError) as e:
        loader.load(path)

    # --- Assert ---
    assert "empty" in str(e.value).lower()


def test_yaml_with_extra_field_raises_configerror(tmp_yaml: Path):
    """
    @brief
    Extra field in YAML causes validation error.

    @details
    Adds an unexpected key to configuration to confirm
    schema validation rejects unknown fields.
    """
    # --- Arrange ---
    data = yaml.safe_load(tmp_yaml.read_text())
    data["extra_field"] = 42
    tmp_yaml.write_text(yaml.safe_dump(data), encoding="utf-8")
    loader = ConfigLoader()

    # --- Act / Assert ---
    with pytest.raises(ConfigError) as e:
        loader.load(tmp_yaml)

    # --- Assert ---
    assert "extra" in str(e.value).lower()


def test_invalid_type_raises_configerror(tmp_yaml: Path):
    """
    @brief
    Invalid field type triggers ConfigError.

    @details
    Writes non-numeric value for numeric field to ensure
    Pydantic schema detects type mismatch.
    """
    # --- Arrange ---
    data = yaml.safe_load(tmp_yaml.read_text())
    data["rooms_max"] = "twenty"
    tmp_yaml.write_text(yaml.safe_dump(data), encoding="utf-8")
    loader = ConfigLoader()

    # --- Act / Assert ---
    with pytest.raises(ConfigError) as e:
        loader.load(tmp_yaml)

    # --- Assert ---
    assert "Invalid configuration" in str(e.value) or "rooms_max" in str(e.value)


def test_invalid_path_type_raises_configerror(tmp_path: Path):
    """
    @brief
    Non-Path argument triggers ConfigError.

    @details
    Passes string instead of Path object to ensure
    type validation in `_read_yaml` works as intended.
    """
    # --- Arrange ---
    loader = ConfigLoader()
    wrong_type = str(tmp_path / "config.yaml")

    # --- Act / Assert ---
    with pytest.raises(ConfigError) as e:
        loader._read_yaml(wrong_type)

    # --- Assert ---
    msg = str(e.value)
    assert "Invalid path type" in msg
    assert "pathlib.Path" in msg


def test_yaml_parsing_error_raises_configerror(tmp_path: Path):
    """
    @brief
    Corrupted YAML triggers ConfigError.

    @details
    Writes malformed YAML to file to simulate
    `yaml.YAMLError` branch in `_read_yaml`.
    """
    # --- Arrange ---
    path = tmp_path / "config.yaml"
    path.write_text("rooms_max: '20\nshift_min: 5", encoding="utf-8")
    loader = ConfigLoader()

    # --- Act / Assert ---
    with pytest.raises(ConfigError) as e:
        loader._read_yaml(path)

    # --- Assert ---
    msg = str(e.value)
    assert "YAML parsing failed" in msg
    assert "Fix YAML syntax" in msg


def test_unable_to_read_file_raises_configerror(monkeypatch, tmp_path: Path):
    """
    @brief
    Simulates OSError when opening file.

    @details
    Patches `Path.open` to raise `OSError` to ensure
    ConfigError is raised with diagnostic message.
    """
    # --- Arrange ---
    path = tmp_path / "config.yaml"
    path.write_text("rooms_max: 10", encoding="utf-8")

    def fake_open(*args, **kwargs):
        raise OSError("Permission denied")

    monkeypatch.setattr(Path, "open", fake_open)
    loader = ConfigLoader()

    # --- Act / Assert ---
    with pytest.raises(ConfigError) as e:
        loader._read_yaml(path)

    # --- Assert ---
    msg = str(e.value)
    assert "Unable to read configuration file" in msg
    assert "Permission denied" in msg


def test_yaml_root_not_mapping_raises_configerror(tmp_path: Path):
    """
    @brief
    Non-mapping YAML root triggers ConfigError.

    @details
    Verifies detection of invalid YAML structure when
    the root element is a list rather than a key-value mapping.
    """
    # --- Arrange ---
    path = tmp_path / "config.yaml"
    path.write_text("- one\n- two\n- three\n", encoding="utf-8")
    loader = ConfigLoader()

    # --- Act / Assert ---
    with pytest.raises(ConfigError) as e:
        loader._read_yaml(path)

    # --- Assert ---
    msg = str(e.value)
    assert "Configuration root must be a mapping" in msg
    assert "key: value" in msg
