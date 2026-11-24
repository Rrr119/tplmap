# Jinja2 / Twig / FreeMarker detection-rate comparison

Generated: 2026-11-25 00:29:49+0800  |  Python 3.14.4

Each range runs the real template engine. `baseline` uses tplmap's canonical probe only; `variants` additionally tries the payload catalogue and variant fallback (`--variants`).

## Detection rate by range

| Range (engine) | Cases | Baseline detected | Baseline rate | With variants | Variant rate | Gained cases |
|---|---:|---:|---:|---:|---:|---|
| Jinja2 | 8 | 6 | 75% | 8 | 100% | filter_canonical_text, filter_operator_wrapped |
| Twig | 8 | 6 | 75% | 8 | 100% | filter_canonical_text, filter_quotes_wrapped |
| Freemarker | 8 | 6 | 75% | 8 | 100% | filter_canonical_text, filter_directive_wrapped |

## Per-case detail

### Jinja2

| Case | Context (L/C) | Filter | Baseline | Variants | Rescue variant |
|---|---|---|---|---|---|
| text | 0/0 | - | detected | detected | - |
| wrapped | 0/0 | - | detected | detected | - |
| echo_tag_compact | 1/1 | - | detected | detected | - |
| quoted_string | 1/1 | - | detected | detected | - |
| if_block | 1/1 | - | detected | detected | - |
| comment_block | 5/1 | - | detected | detected | - |
| filter_canonical_text | 0/0 | filter_canonical | missed | detected | math_7x7 |
| filter_operator_wrapped | 0/0 | filter_secondary | missed | detected | tilde_concat |

### Twig

| Case | Context (L/C) | Filter | Baseline | Variants | Rescue variant |
|---|---|---|---|---|---|
| text | 0/0 | - | detected | detected | - |
| wrapped | 0/0 | - | detected | detected | - |
| echo_tag_spaced | 1/0 | - | detected | detected | - |
| set_quoted | 1/0 | - | detected | detected | - |
| if_block | 1/0 | - | detected | detected | - |
| for_loop | 5/1 | - | detected | detected | - |
| filter_canonical_text | 0/0 | filter_canonical | missed | detected | math_7x7 |
| filter_quotes_wrapped | 0/0 | filter_secondary | missed | detected | math_7x7 |

### Freemarker

| Case | Context (L/C) | Filter | Baseline | Variants | Rescue variant |
|---|---|---|---|---|---|
| text | 0/0 | - | detected | detected | - |
| wrapped | 0/0 | - | detected | detected | - |
| interpolation_spaced | 1/0 | - | detected | detected | - |
| assign_directive | 2/1 | - | detected | detected | - |
| comment_directive | 5/1 | - | detected | detected | - |
| if_right_operand | 2/1 | - | detected | detected | - |
| filter_canonical_text | 0/0 | filter_canonical | missed | detected | interpolation_7x7 |
| filter_directive_wrapped | 0/0 | filter_secondary | missed | detected | interpolation_7x7 |

## Payload variant coverage (unfiltered cases)

| Variant | Hits / runs | Rate |
|---|---:|---:|
| jinja2/list_join_filter | 6/6 | 100% |
| jinja2/math_7x7 | 6/6 | 100% |
| jinja2/math_random_mul | 6/6 | 100% |
| jinja2/power_operator | 6/6 | 100% |
| jinja2/string_multiply_python | 6/6 | 100% |
| jinja2/tilde_concat | 6/6 | 100% |
| jinja2/upper_filter | 6/6 | 100% |
| twig/abs_filter | 6/6 | 100% |
| twig/array_join_filter | 6/6 | 100% |
| twig/math_7x7 | 6/6 | 100% |
| twig/math_random_mul | 6/6 | 100% |
| twig/string_multiply_coerced | 6/6 | 100% |
| twig/tilde_concat | 6/6 | 100% |
| twig/upper_filter | 6/6 | 100% |
| freemarker/assign_then_multiply | 6/6 | 100% |
| freemarker/computer_format_c | 6/6 | 100% |
| freemarker/interpolation_7x7 | 6/6 | 100% |
| freemarker/interpolation_random_mul | 6/6 | 100% |
| freemarker/plus_concat | 6/6 | 100% |
| freemarker/sequence_join_builtin | 6/6 | 100% |
| freemarker/upper_case_builtin | 6/6 | 100% |

## CLI compatibility checks

| Check | Result | Evidence |
|---|---|---|
| cli_help_lists_variants | PASS | exit 0 |
| cli_list_variants | PASS | exit 0 |
| cli_jinja2 | PASS | engine listed=True, variants=7/7, 0.2s |
| cli_jinja2_filter_canonical | PASS | engine listed=True, variants=6/7, 0.1s |
| cli_twig | PASS | engine listed=True, variants=7/7, 0.2s |
| cli_twig_filter_canonical | PASS | engine listed=True, variants=7/7, 0.2s |
| cli_freemarker | PASS | engine listed=True, variants=7/7, 0.2s |
| cli_freemarker_filter_canonical | PASS | engine listed=True, variants=7/7, 0.2s |

## Reproduce

```bash
python3 benchmarks/run_comparison.py
python3 -m unittest tests.test_engine_variants -v
```
