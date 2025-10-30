\# docs/schemas.md - Data Schemas Reference



This document defines the canonical data structures used by the Opmed optimization system.  

All modules must conform to these schemas for data serialization, validation, and reproducibility.



---



\## 1. Surgery Schema



Represents a single surgery entry from surgeries.csv.



| Field | Type | Required | Default | Description |

|--------|------|----------|----------|-------------|

| surgery\_id | string | yes | - | Unique identifier |

| start\_time | datetime (ISO-8601, UTC) | yes | - | Surgery start time |

| end\_time | datetime (ISO-8601, UTC) | yes | - | Surgery end time |

| duration | float (hours) | optional | computed | Duration = (end\_time - start\_time) |

| room\_hint | string | optional | null | Preferred operating room |



Validation rules:

\- start\_time < end\_time

\- duration > 0

\- timezone must be explicit (UTC or from config)

\- converted to integer ticks during model building



Example (CSV):

surgery\_id,start\_time,end\_time,duration,room\_hint

S001,2025-10-29T08:30:00Z,2025-10-29T10:15:00Z,1.75,A1



---



\## 2. Config Schema



Represents parameters loaded from config.yaml.



| Field | Type | Default | Description |

|--------|------|----------|-------------|

| time\_unit | float | 0.0833 | Tick size in hours (5 min) |

| rooms\_max | int | 20 | Maximum number of operating rooms |

| shift\_min | float | 5 | Minimum shift length in hours |

| shift\_max | float | 12 | Maximum shift length in hours |

| shift\_overtime | float | 9 | Overtime threshold (hours) |

| overtime\_multiplier | float | 1.5 | Overtime cost multiplier |

| buffer | float | 0.25 | Room-change buffer in hours |

| utilization\_target | float | 0.8 | Required minimum utilization |

| enforce\_surgery\_duration\_limit | bool | True | Reject surgeries longer than 12h |

| timezone | string | UTC | Default timezone for datetime parsing |

| solver.search\_branching | string | AUTOMATIC | CP-SAT search mode |

| solver.num\_workers | int | 4 | Number of threads |

| solver.max\_time\_in\_seconds | int | 60 | Solver time limit |

| solver.random\_seed | int | 0 | Random seed for reproducibility |



Validation rules:

\- shift\_min >= 5, shift\_max <= 12, shift\_min < shift\_max

\- buffer > 0

\- utilization\_target between 0 and 1

\- time\_unit > 0

\- all numeric values positive



Example (YAML):

time\_unit: 0.0833

rooms\_max: 20

shift\_min: 5

shift\_max: 12

shift\_overtime: 9

overtime\_multiplier: 1.5

buffer: 0.25

utilization\_target: 0.8

enforce\_surgery\_duration\_limit: true

timezone: UTC

solver:

&nbsp; search\_branching: AUTOMATIC

&nbsp; num\_workers: 8

&nbsp; max\_time\_in\_seconds: 60

&nbsp; random\_seed: 42



---



\## 3. SolutionRow Schema



Represents one record from solution.csv.



| Field | Type | Required | Default | Description |

|--------|------|----------|----------|-------------|

| surgery\_id | string | yes | - | Must match input surgery |

| start\_time | datetime (ISO-8601, UTC) | yes | - | Scheduled start |

| end\_time | datetime (ISO-8601, UTC) | yes | - | Scheduled end |

| anesthetist\_id | string | yes | - | Assigned anesthesiologist |

| room\_id | string | yes | - | Assigned operating room |



Validation rules:

\- surgery\_id exists in surgeries.csv

\- start\_time < end\_time

\- no overlapping intervals for same anesthetist\_id or room\_id

\- buffer >= 15 minutes enforced between room switches

\- output sorted by anesthetist\_id, start\_time



Example (CSV):

surgery\_id,start\_time,end\_time,anesthetist\_id,room\_id

S001,2025-10-29T08:30:00Z,2025-10-29T10:15:00Z,A05,R1

S002,2025-10-29T09:45:00Z,2025-10-29T12:00:00Z,A12,R2



---



\## 4. Timezone and Tick Conversion Rules



| Concept | Description |

|----------|-------------|

| timezone | All datetimes are stored as UTC by default. Local zones are supported through Config.timezone. |

| delta\_t | Default time unit = 0.0833 hours (5 minutes). |

| tick formula | tick = round((timestamp - day\_start) / delta\_t) |

| back conversion | datetime = day\_start + tick \* delta\_t |

| allowed error | <= 1 percent discretization tolerance |



These conversion rules ensure deterministic rounding and reproducible time reasoning in the CP-SAT solver.



---



\## 5. Schema Versioning

\- Schema changes must be versioned via git and documented in ADRs.  

\- Backward compatibility for input/output is mandatory within one major release.  

\- Validation errors must raise ConfigError or DataError according to ADR-008.



---



End of file.

