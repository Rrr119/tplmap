# Local SSTI ranges (Jinja2 / Twig / FreeMarker)

Three minimal target applications using the **real** template engines, with
the same request contract as the upstream Docker ranges:

```
GET /reflect/<engine>?tpl=<template containing a literal %s>&inj=<payload>
```

The server replaces `%s` with `inj` and renders the template.

| Engine | Stack | Entry point | Default port |
|---|---|---|---:|
| Jinja2 | Python stdlib HTTP + Jinja2 | `ranges/jinja2_range.py` | 15011 |
| Twig | PHP built-in server + Twig 3 | `ranges/twig_range/router.php` | 15012 |
| FreeMarker | JDK `HttpServer` + FreeMarker | `ranges/freemarker_range/FreemarkerRange.java` | 15013 |

Every range also exposes:

- `/health` - liveness probe;
- `/reflect/<engine>/filter_canonical` - blocks the stock canonical probe
  (Jinja2 `,`, Twig `nl2br`, FreeMarker `<#--`);
- `/reflect/<engine>/filter_secondary` - blocks another token (`*`, `"`, `<#`).

The filters model weak WAF/input filtering and show why payload variants
improve detection rate.

## Runtime setup

The benchmark and tests spawn the ranges on ephemeral ports through
`ranges/harness.py`. Install the optional local runtimes once with:

```bash
bash ranges/setup_runtimes.sh
```

Runtimes are placed in `.runtimes/` (static PHP + Twig, Temurin JDK,
`freemarker.jar`). Jinja2 is imported from the active Python. Missing
runtimes only skip the corresponding live tests; the catalogue/CLI tests
always run.

## Run the comparison

```bash
python3 benchmarks/run_comparison.py
```

Outputs `artifacts/detection_comparison.md` and
`artifacts/detection_comparison.json`.

## Run the tests

```bash
python3 -m unittest tests.test_engine_variants -v
```
