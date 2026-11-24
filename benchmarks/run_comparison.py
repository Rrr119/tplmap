#!/usr/bin/env python3
"""Detection-rate comparison across the Jinja2/Twig/FreeMarker ranges.

For every local target range a fixed matrix of injection cases is probed in
two modes:

* baseline  - stock tplmap canonical ``test_render`` probe only;
* variants  - ``--variants`` mode, which can rescue detection with the
              additional payload catalogue and reports per-variant hits.

The script writes ``artifacts/detection_comparison.json`` and
``artifacts/detection_comparison.md`` and prints the markdown table.

Usage:

    python3 benchmarks/run_comparison.py
    python3 benchmarks/run_comparison.py --no-cli
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import logging

from utils import loggers as _loggers  # noqa: E402

_loggers.stream_handler.setLevel(logging.CRITICAL)

from core.channel import Channel  # noqa: E402
from core.checks import detect_template_injection  # noqa: E402
from core.variants import run_suite  # noqa: E402
from plugins.engines.jinja2 import Jinja2  # noqa: E402
from plugins.engines.twig import Twig  # noqa: E402
from plugins.engines.freemarker import Freemarker  # noqa: E402
from ranges import harness  # noqa: E402


ENGINE_CLASSES = {
    "jinja2": Jinja2,
    "twig": Twig,
    "freemarker": Freemarker,
}

# (case id, server-side template with literal %s, level, clevel, filter path)
SCENARIOS = {
    "jinja2": [
        ("text", "%s", 0, 0, None),
        ("wrapped", "AAA%sAAA", 0, 0, None),
        ("echo_tag_compact", "{{%s}}", 1, 1, None),
        ("quoted_string", "{{ '%s' }}", 1, 1, None),
        ("if_block", "{% if %s: %}{% endif %}", 1, 1, None),
        ("comment_block", "{# %s #}", 5, 1, None),
        ("filter_canonical_text", "%s", 0, 0, "filter_canonical"),
        ("filter_operator_wrapped", "AAA%sAAA", 0, 0, "filter_secondary"),
    ],
    "twig": [
        ("text", "%s", 0, 0, None),
        ("wrapped", "AAA%sAAA", 0, 0, None),
        ("echo_tag_spaced", "{{ %s }}", 1, 0, None),
        ("set_quoted", "{% set foo = '%s' %}", 1, 0, None),
        ("if_block", "{% if %s == 1 %}{% endif %}", 1, 0, None),
        ("for_loop", "{% for item in %s %}{% endfor %}", 5, 1, None),
        ("filter_canonical_text", "%s", 0, 0, "filter_canonical"),
        ("filter_quotes_wrapped", "AAA%sAAA", 0, 0, "filter_secondary"),
    ],
    "freemarker": [
        ("text", "%s", 0, 0, None),
        ("wrapped", "AAA%sAAA", 0, 0, None),
        ("interpolation_spaced", "${ %s }", 1, 0, None),
        ("assign_directive", "<#assign s = %s>", 2, 1, None),
        ("comment_directive", "<#-- %s -->", 5, 1, None),
        ("if_right_operand", "<#if 1 == %s></#if>", 2, 1, None),
        ("filter_canonical_text", "%s", 0, 0, "filter_canonical"),
        ("filter_directive_wrapped", "AAA%sAAA", 0, 0, "filter_secondary"),
    ],
}

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def build_case_url(base_url, engine, scenario):
    _case_id, template, _level, _clevel, filter_name = scenario
    path = "/reflect/%s" % engine
    if filter_name:
        path += "/" + filter_name
    query = urllib.parse.urlencode({"tpl": template})
    return "%s%s?%s&inj=*" % (base_url, path, query)


def _base_args(url, scenario, with_variants):
    _case_id, _template, level, clevel, _filter = scenario
    args = {
        "url": url,
        "force_level": [level, clevel],
        "injection_tag": "*",
        "technique": "R",
    }
    if with_variants:
        args["payload_variants"] = True
    return args


def run_case(base_url, engine, scenario):
    """Run baseline and variant-enhanced detection for one case."""

    plugin_cls = ENGINE_CLASSES[engine]
    url = build_case_url(base_url, engine, scenario)

    baseline_channel = Channel(_base_args(url, scenario, False))
    baseline_plugin = detect_template_injection(baseline_channel, plugins=[plugin_cls])
    baseline_hit = baseline_channel.data.get("engine") == engine

    enhanced_channel = Channel(_base_args(url, scenario, True))
    enhanced_plugin = detect_template_injection(enhanced_channel, plugins=[plugin_cls])
    enhanced_hit = enhanced_channel.data.get("engine") == engine
    detection_variant = enhanced_channel.data.get("detection_variant")

    variant_results = None
    if enhanced_hit and enhanced_plugin is not None:
        variant_results = run_suite(enhanced_plugin)

    return {
        "id": scenario[0],
        "template": scenario[1],
        "level": scenario[2],
        "clevel": scenario[3],
        "filter": scenario[4],
        "url": url,
        "baseline_detected": baseline_hit,
        "variants_detected": enhanced_hit,
        "rescued_by_variant": (
            detection_variant if enhanced_hit and not baseline_hit else None
        ),
        "detection_variant": detection_variant,
        "variant_suite": variant_results,
    }


def run_cli_smoke(base_url, engine, filter_name=None, timeout=180):
    """Invoke the stock tplmap CLI as a subprocess and parse the result."""

    path = "/reflect/%s" % engine
    if filter_name:
        path += "/" + filter_name
    query = urllib.parse.urlencode({"tpl": "%s"})
    url = "%s%s?%s&inj=*" % (base_url, path, query)

    argv = [
        sys.executable,
        os.path.join(ROOT, "tplmap.py"),
        "-u",
        url,
        "-e",
        engine.capitalize(),
        "-t",
        "R",
        "--variants",
    ]

    started = time.time()
    try:
        proc = subprocess.run(
            argv,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = ANSI_RE.sub("", (proc.stdout or "") + "\n" + (proc.stderr or ""))
        summary_match = re.search(r"(\d+)/(\d+) variants confirmed", output)
        return {
            "name": "cli_%s%s" % (engine, ("_" + filter_name) if filter_name else ""),
            "argv": argv,
            "returncode": proc.returncode,
            "elapsed": round(time.time() - started, 2),
            "engine_listed": ("Engine: %s" % engine.capitalize()) in output,
            "variant_summary": summary_match.groups() if summary_match else None,
            "fallback_listed": "confirmed with payload variant" in output
            or "detection confirmed by fallback variant" in output,
            "tail": "\n".join(output.strip().splitlines()[-6:]),
        }
    except subprocess.TimeoutExpired:
        return {
            "name": "cli_%s" % engine,
            "argv": argv,
            "timeout": timeout,
            "engine_listed": False,
            "error": "timeout after %ss" % timeout,
        }


def run_static_cli_checks():
    """Checks that do not need a target: -h and --list-variants."""

    results = []

    help_proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tplmap.py"), "-h"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    help_out = ANSI_RE.sub("", help_proc.stdout + help_proc.stderr)
    results.append(
        {
            "name": "cli_help_lists_variants",
            "returncode": help_proc.returncode,
            "ok": "--variants" in help_out and "--list-variants" in help_out,
        }
    )

    list_proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tplmap.py"), "--list-variants"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    list_out = ANSI_RE.sub("", list_proc.stdout + list_proc.stderr)
    results.append(
        {
            "name": "cli_list_variants",
            "returncode": list_proc.returncode,
            "ok": (
                list_proc.returncode == 0
                and all(name in list_out for name in ("Jinja2", "Twig", "Freemarker"))
            ),
        }
    )

    return results


def _aggregate_variant_hits(cases):
    totals = {}
    for case in cases:
        if case.get("filter"):
            continue  # only unfiltered cases measure catalogue coverage
        for record in case.get("variant_suite") or []:
            stat = totals.setdefault(
                record["name"], {"hits": 0, "runs": 0, "engines": set()}
            )
            stat["runs"] += 1
            if record["hit"]:
                stat["hits"] += 1
                stat["engines"].add(case["_engine"])
    return totals


def run_comparison(engines=("jinja2", "twig", "freemarker"), run_cli=True):
    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S%z"),
        "python": sys.version.split()[0],
        "availability": {
            k: v
            for k, v in harness.availability().items()
            if k in ("jinja2", "twig", "freemarker")
        },
        "engines": {},
        "cli": [],
        "static_cli": run_static_cli_checks(),
    }

    with harness.spawn_all(only=list(engines)) as ranges:
        for engine in engines:
            process = ranges.get(engine)
            if process is None:
                report["engines"][engine] = {"skipped": "runtime unavailable"}
                continue

            cases = []
            for scenario in SCENARIOS[engine]:
                result = run_case(process.base_url, engine, scenario)
                result["_engine"] = engine
                cases.append(result)

            total = len(cases)
            baseline_hits = sum(c["baseline_detected"] for c in cases)
            enhanced_hits = sum(c["variants_detected"] for c in cases)

            variant_stats = {}
            for name, stat in _aggregate_variant_hits(cases).items():
                variant_stats[name] = {
                    "hits": stat["hits"],
                    "runs": stat["runs"],
                    "hit_rate": round(stat["hits"] / stat["runs"], 3),
                }

            report["engines"][engine] = {
                "range_url": process.base_url,
                "total_cases": total,
                "baseline_detected": baseline_hits,
                "variants_detected": enhanced_hits,
                "baseline_rate": round(baseline_hits / total, 4),
                "variants_rate": round(enhanced_hits / total, 4),
                "gained": [
                    c["id"]
                    for c in cases
                    if c["variants_detected"] and not c["baseline_detected"]
                ],
                "variant_hits": variant_stats,
                "cases": cases,
            }

            if run_cli:
                report["cli"].append(run_cli_smoke(process.base_url, engine))
                report["cli"].append(
                    run_cli_smoke(process.base_url, engine, "filter_canonical")
                )

    return report


def render_markdown(report):
    lines = [
        "# Jinja2 / Twig / FreeMarker detection-rate comparison",
        "",
        "Generated: %s  |  Python %s" % (report["generated_at"], report["python"]),
        "",
        "Each range runs the real template engine. `baseline` uses tplmap's "
        "canonical probe only; `variants` additionally tries the payload "
        "catalogue and variant fallback (`--variants`).",
        "",
        "## Detection rate by range",
        "",
        "| Range (engine) | Cases | Baseline detected | Baseline rate | With variants | Variant rate | Gained cases |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]

    for engine, data in report["engines"].items():
        if data.get("skipped"):
            lines.append("| %s | - | skipped (%s) | - | - | - | - |" % (engine, data["skipped"]))
            continue
        lines.append(
            "| %s | %i | %i | %.0f%% | %i | %.0f%% | %s |"
            % (
                engine.capitalize(),
                data["total_cases"],
                data["baseline_detected"],
                data["baseline_rate"] * 100,
                data["variants_detected"],
                data["variants_rate"] * 100,
                ", ".join(data["gained"]) or "-",
            )
        )

    lines += ["", "## Per-case detail", ""]
    for engine, data in report["engines"].items():
        if data.get("skipped"):
            continue
        lines += ["### %s" % engine.capitalize(), "",
                  "| Case | Context (L/C) | Filter | Baseline | Variants | Rescue variant |",
                  "|---|---|---|---|---|---|"]
        for case in data["cases"]:
            lines.append(
                "| %s | %s/%s | %s | %s | %s | %s |"
                % (
                    case["id"],
                    case["level"],
                    case["clevel"],
                    case["filter"] or "-",
                    "detected" if case["baseline_detected"] else "missed",
                    "detected" if case["variants_detected"] else "missed",
                    case["rescued_by_variant"] or "-",
                )
            )
        lines.append("")

    lines += ["## Payload variant coverage (unfiltered cases)", "",
              "| Variant | Hits / runs | Rate |", "|---|---:|---:|"]
    for engine, data in report["engines"].items():
        if data.get("skipped"):
            continue
        for name, stat in sorted(data["variant_hits"].items()):
            lines.append(
                "| %s/%s | %i/%i | %.0f%% |"
                % (engine, name, stat["hits"], stat["runs"], stat["hit_rate"] * 100)
            )
    lines.append("")

    lines += ["## CLI compatibility checks", "",
              "| Check | Result | Evidence |", "|---|---|---|"]
    for check in report.get("static_cli", []):
        lines.append(
            "| %s | %s | exit %s |"
            % (check["name"], "PASS" if check.get("ok") else "FAIL", check.get("returncode"))
        )
    for check in report.get("cli", []):
        if check.get("error"):
            lines.append("| %s | ERROR | %s |" % (check["name"], check["error"]))
            continue
        summary = check.get("variant_summary")
        evidence = "engine listed=%s, variants=%s, %.1fs" % (
            check.get("engine_listed"),
            ("%s/%s" % summary[0:2] if summary else "n/a"),
            check.get("elapsed", 0),
        )
        lines.append(
            "| %s | %s | %s |"
            % (check["name"], "PASS" if check.get("engine_listed") else "FAIL", evidence)
        )
    lines.append("")
    lines += [
        "## Reproduce",
        "",
        "```bash",
        "python3 benchmarks/run_comparison.py",
        "python3 -m unittest tests.test_engine_variants -v",
        "```",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=os.path.join(ROOT, "artifacts"))
    parser.add_argument("--no-cli", action="store_true", help="skip CLI subprocess checks")
    parser.add_argument(
        "--engines",
        default="jinja2,twig,freemarker",
        help="comma separated subset of engines",
    )
    args = parser.parse_args()

    engines = tuple(e.strip() for e in args.engines.split(",") if e.strip())
    report = run_comparison(engines=engines, run_cli=not args.no_cli)

    os.makedirs(args.out_dir, exist_ok=True)
    json_path = os.path.join(args.out_dir, "detection_comparison.json")
    md_path = os.path.join(args.out_dir, "detection_comparison.md")

    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False, default=str)
    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write(render_markdown(report))

    print(render_markdown(report))
    print("\nWrote %s and %s" % (json_path, md_path))


if __name__ == "__main__":
    main()
