\## Context

The Opmed optimization system uses configuration files to control solver parameters, time discretization, validation thresholds, and experiment metadata.

Consistency of configuration parsing is essential for reproducibility, CI/CD automation, and integration with MLOps tools such as Airflow and MLflow.



Early prototypes relied on ad-hoc dictionaries or manual parsing of YAML files, which caused missing defaults, type errors, and inconsistent validation.

This decision defines the configuration standard, file format, schema enforcement, and the Python validation mechanism.



\## Decision

Adopt YAML as the human-readable configuration format, validated by Pydantic models at runtime.



\### Configuration file

All solver parameters and constants are stored in config.yaml at the project root or experiment directory.



Example:

\# config.yaml

time\_unit: 0.0833       # 5 minutes

rooms\_max: 20

shift\_min: 5

shift\_max: 12

shift\_overtime: 9

overtime\_multiplier: 1.5

buffer: 0.25

utilization\_target: 0.8

enforce\_surgery\_duration\_limit: true



solver:

&nbsp; search\_branching: AUTOMATIC

&nbsp; num\_workers: 8

&nbsp; max\_time\_in\_seconds: 60

&nbsp; random\_seed: 42



\### Validation layer

The module opmed.dataloader.config\_loader defines Pydantic models:

class SolverParams(BaseModel):

&nbsp;   search\_branching: str = "AUTOMATIC"

&nbsp;   num\_workers: int = 4

&nbsp;   max\_time\_in\_seconds: int = 60

&nbsp;   random\_seed: int = 0



class Config(BaseModel):

&nbsp;   time\_unit: float = 0.0833

&nbsp;   rooms\_max: int = 20

&nbsp;   shift\_min: float = 5

&nbsp;   shift\_max: float = 12

&nbsp;   shift\_overtime: float = 9

&nbsp;   overtime\_multiplier: float = 1.5

&nbsp;   buffer: float = 0.25

&nbsp;   utilization\_target: float = 0.8

&nbsp;   enforce\_surgery\_duration\_limit: bool = True

&nbsp;   solver: SolverParams = SolverParams()



All modules receive the validated Config object rather than re-parsing YAML.

Invalid or missing fields raise ConfigError with a clear diagnostic message.



\## Alternatives

1\. JSON configuration

&nbsp;  Pros: simpler parsing, native to Python.

&nbsp;  Cons: less readable, does not support comments, poor for long parameter sets.



2\. TOML configuration

&nbsp;  Pros: structured, standard for Python packaging.

&nbsp;  Cons: lacks YAML-style nesting for complex solver configs.



3\. INI files or environment variables

&nbsp;  Pros: minimal dependencies.

&nbsp;  Cons: weak typing, limited nesting, poor reproducibility.



YAML + Pydantic provides human readability, strong typing, and strict runtime validation.



\## Consequences

\- Configuration errors are detected early at load time.

\- Default values are centralized in Pydantic models.

\- Reproducibility improves through deterministic config serialization.

\- Easy integration with experiment tracking (MLflow stores serialized config).

\- CI pipelines can validate config consistency automatically.



Risk: YAML syntax errors must be caught with clear user feedback; handled by ConfigError exceptions.



\## Status

Status: Accepted

Date: 2025-10-30

Authors: Algorithm Research Team

Related Tasks: Epic 3 -> 3.1.5, T1.1.5 (Logical Scheme), T2.3.5 (Theoretical Model.md)



This decision defines YAML + Pydantic as the unified configuration management standard for all Opmed modules, ensuring consistent validation and reproducible solver behavior.

"@ | Out-File -Encoding ascii "C:\\Repository\\opmed-optimization\\ADRs\\ADR-004-configuration-management.md"
