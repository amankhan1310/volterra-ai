# backend

VOLTERRA AI backend. Phase 2 provides `app/analytics`, a standard-library-only Python port of the
legacy prototype's analytics (the **v1** algorithms), verified against the golden fixtures in
[`tests/golden/`](tests/golden/README.md). The FastAPI service, database and migrations arrive
in Phase 3 (see [`../ARCHITECTURE_PLAN.md`](../ARCHITECTURE_PLAN.md)).

## Layout

| Module                   | Ports                                                                 |
| ------------------------ | --------------------------------------------------------------------- |
| `analytics/jsmath.py`    | JavaScript number semantics (summation order, rounding, `toFixed`, …) |
| `analytics/prng.py`      | mulberry32                                                            |
| `analytics/synthetic.py` | synthetic-v1 dataset                                                  |
| `analytics/stats.py`     | `lin` (OLS) and `median`                                              |
| `analytics/health.py`    | SOH now, fade, RUL and interval, forecast, gauge                      |
| `analytics/backtest.py`  | time-ordered backtest                                                 |
| `analytics/anomalies.py` | robust z-score detector v1                                            |
| `analytics/simulator.py` | what-if simulator v1                                                  |
| `analytics/advisor.py`   | Charging Advisor (ui.js semantics)                                    |
| `analytics/insights.py`  | insights v1 (structured kind/text/values)                             |
| `analytics/display.py`   | health level and condition label                                      |
| `analytics/legacy_v1.py` | `analyze()`: every v1 result in one immutable object                  |

v1 reproduces the prototype exactly, including known defects F1–F8. Those are documented as
strict expected-failure tests in `tests/parity/test_known_defects.py`. Fixes will be separate v2
implementations, and v1 is never changed.

## Development

Requires [uv](https://docs.astral.sh/uv/) (CI uses 0.12.24) and Python 3.10 or newer.

```sh
cd backend
uv sync --locked                   # create .venv from uv.lock
uv run ruff check . && uv run ruff format --check .
uv run mypy                        # strict
uv run pytest                      # parity + unit tests, coverage gate 85%
```

The pytest summary includes a **golden parity** table. It shows how many numeric comparisons
were bit-exact and how many needed the 1e-12 tolerance. That tolerance is allowed only for
fields derived from `sin`, `exp` or `pow`.

## Rules for analytics code

- Use the standard library only, and mirror the JavaScript expression order.
- Never use `sum()`, `round()` or `math.fsum`. Use `jsmath.reduce_add`, `jsmath.sum_from_zero`
  and `jsmath.js_round`. `tests/unit/test_source_hygiene.py` enforces this.
- Never edit `tests/golden/*.json`. They are generated from `legacy/` by
  `legacy/tools/export_golden.js`.
