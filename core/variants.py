"""
Additional payload variants for server-side template injection detection.

The stock tplmap engines ship a single canonical ``test_render`` probe.
Real-world targets sometimes disturb that exact probe (keyword filters,
WAF rules, engine minor versions, ...) while still evaluating equivalent
expressions. This module provides a small catalogue of independent,
verifiable payload variants for the three engines covered by this task:
Jinja2, Twig and FreeMarker.

Every variant is described by a plain dict:

    {
        "name":        stable identifier,
        "description": human readable explanation,
        "code":        code handed to ``plugin.render(code=...)``,
        "match":       "equals" | "contains" | "regex",
        "expected":    expected output / substring / regex pattern,
    }

The variants are deliberately side-effect free (arithmetic and string
operations only) so they can safely be used during detection.
"""

import re

from utils import rand


ENGINES = ("jinja2", "twig", "freemarker")


def _letters(n):
    return rand.randstr_n(n, "abcdefghijklmnopqrstuvwxyz")


def build_variants(engine):
    """Return a fresh list of payload variant dicts for ``engine``.

    Random operands are generated per call so repeated scans do not reuse
    predictable values. Returns an empty list for unsupported engines.
    """

    engine = (engine or "").lower()

    if engine == "jinja2":
        a, b = rand.randint_n(2), rand.randint_n(1)
        s1, s2 = _letters(5), _letters(6)
        upper = _letters(7)
        return [
            {
                "name": "math_7x7",
                "description": "Compact arithmetic canary {{7*7}}",
                "code": "7*7",
                "match": "equals",
                "expected": "49",
            },
            {
                "name": "math_random_mul",
                "description": "Randomised arithmetic expression",
                "code": "%(a)d*%(b)d" % {"a": a, "b": b},
                "match": "equals",
                "expected": str(a * b),
            },
            {
                "name": "string_multiply_python",
                "description": "Jinja2/Python string repetition 7*'7' -> 7777777",
                "code": "7*'7'",
                "match": "equals",
                "expected": "7" * 7,
            },
            {
                "name": "tilde_concat",
                "description": "Tilde string concatenation",
                "code": "'%(s1)s'~'%(s2)s'" % {"s1": s1, "s2": s2},
                "match": "equals",
                "expected": s1 + s2,
            },
            {
                "name": "upper_filter",
                "description": "Upper-case filter on a random string",
                "code": "'%(s)s'|upper" % {"s": upper},
                "match": "equals",
                "expected": upper.upper(),
            },
            {
                "name": "power_operator",
                "description": "Power operator 2**8",
                "code": "2**8",
                "match": "equals",
                "expected": "256",
            },
            {
                "name": "list_join_filter",
                "description": "List literal joined with a dash",
                "code": "['%(s1)s','%(s2)s']|join('-')" % {"s1": s1, "s2": s2},
                "match": "equals",
                "expected": "%s-%s" % (s1, s2),
            },
        ]

    if engine == "twig":
        a, b = rand.randint_n(2), rand.randint_n(1)
        negative = rand.randint_n(2)
        s1, s2 = _letters(5), _letters(6)
        upper = _letters(7)
        return [
            {
                "name": "math_7x7",
                "description": "Compact arithmetic canary {{7*7}}",
                "code": "7*7",
                "match": "equals",
                "expected": "49",
            },
            {
                "name": "math_random_mul",
                "description": "Randomised arithmetic expression",
                "code": "%(a)d*%(b)d" % {"a": a, "b": b},
                "match": "equals",
                "expected": str(a * b),
            },
            {
                "name": "string_multiply_coerced",
                "description": "Twig coerces the string in 7*'7' -> 49",
                "code": "7*'7'",
                "match": "equals",
                "expected": "49",
            },
            {
                "name": "tilde_concat",
                "description": "Tilde string concatenation",
                "code": "'%(s1)s'~'%(s2)s'" % {"s1": s1, "s2": s2},
                "match": "equals",
                "expected": s1 + s2,
            },
            {
                "name": "upper_filter",
                "description": "Upper filter on a random string",
                "code": "'%(s)s'|upper" % {"s": upper},
                "match": "equals",
                "expected": upper.upper(),
            },
            {
                "name": "abs_filter",
                "description": "Absolute value filter with grouping parentheses",
                "code": "(-%(n)d)|abs" % {"n": negative},
                "match": "equals",
                "expected": str(negative),
            },
            {
                "name": "array_join_filter",
                "description": "Array literal joined with a dash",
                "code": "['%(s1)s','%(s2)s']|join('-')" % {"s1": s1, "s2": s2},
                "match": "equals",
                "expected": "%s-%s" % (s1, s2),
            },
        ]

    if engine == "freemarker":
        # FreeMarker's default number format can add grouping separators for
        # large products, so the plain interpolation variant uses single
        # digit operands while the ?c (computer format) variant covers big
        # random operands.
        small_a, small_b = rand.randint_n(1), rand.randint_n(1)
        a, b = rand.randint_n(2), rand.randint_n(2)
        s1, s2 = _letters(5), _letters(6)
        upper = _letters(7)
        return [
            {
                "name": "interpolation_7x7",
                "description": "Classic ${7*7} interpolation",
                "code": "${7*7}",
                "match": "equals",
                "expected": "49",
            },
            {
                "name": "interpolation_random_mul",
                "description": "Randomised arithmetic interpolation",
                "code": "${%(a)d*%(b)d}" % {"a": small_a, "b": small_b},
                "match": "equals",
                "expected": str(small_a * small_b),
            },
            {
                "name": "computer_format_c",
                "description": "?c computer-formatted random product",
                "code": "${(%(a)d*%(b)d)?c}" % {"a": a, "b": b},
                "match": "equals",
                "expected": str(a * b),
            },
            {
                "name": "assign_then_multiply",
                "description": "<#assign> directive followed by ?c interpolation",
                "code": "<#assign tplmapVar=%(a)d>${(tplmapVar*%(b)d)?c}" % {"a": a, "b": b},
                "match": "equals",
                "expected": str(a * b),
            },
            {
                "name": "upper_case_builtin",
                "description": "?upper_case built-in on a random string",
                "code": "${'%(s)s'?upper_case}" % {"s": upper},
                "match": "equals",
                "expected": upper.upper(),
            },
            {
                "name": "plus_concat",
                "description": "Plus operator string concatenation",
                "code": "${'%(s1)s' + '%(s2)s'}" % {"s1": s1, "s2": s2},
                "match": "equals",
                "expected": s1 + s2,
            },
            {
                "name": "sequence_join_builtin",
                "description": "Sequence literal with ?join built-in",
                "code": "<#assign tplmapSeq=['%(s1)s','%(s2)s']>${tplmapSeq?join('-')}"
                % {"s1": s1, "s2": s2},
                "match": "equals",
                "expected": "%s-%s" % (s1, s2),
            },
        ]

    return []


def score_variant(variant, output):
    """Return True when ``output`` satisfies the variant expectation."""

    if output is None:
        return False

    expected = variant.get("expected", "")
    matcher = variant.get("match", "equals")

    if matcher == "equals":
        return output == expected
    if matcher == "contains":
        return expected in output
    if matcher == "regex":
        return re.search(expected, output) is not None

    return False


def render_preview(plugin, variant):
    """Compose the exact render-template payload for reporting."""

    render_template = (
        plugin.actions.get("render", {}).get("render")
        or plugin.get("render")
        or "%(code)s"
    )
    try:
        return render_template % {"code": variant["code"]}
    except (KeyError, TypeError, ValueError):
        return variant["code"]


def run_suite(plugin):
    """Fire every variant of the plugin's engine through the confirmed context.

    The plugin must already hold a detected render context. Returns a list
    of result records (one per variant). Network/template errors are captured
    per variant instead of aborting the suite.
    """

    engine = getattr(plugin, "plugin", "").lower()
    results = []

    for variant in build_variants(engine):
        record = {
            "name": variant["name"],
            "description": variant["description"],
            "match": variant["match"],
            "expected": variant["expected"],
            "code": variant["code"],
            "payload": render_preview(plugin, variant),
            "hit": False,
            "output": None,
            "error": None,
        }

        try:
            output = plugin.render(code=variant["code"])
            if isinstance(output, str):
                output = output.strip()
            record["output"] = output
            record["hit"] = score_variant(variant, output)
        except Exception as error:  # a failing variant must not kill the scan
            record["error"] = "%s: %s" % (type(error).__name__, error)

        results.append(record)

    return results


def format_report(engine, results, detection_variant=None):
    """Render an ASCII table for the CLI output."""

    lines = []
    lines.append("Payload variants for %s:" % engine.capitalize())
    if detection_variant:
        lines.append("  detection confirmed by fallback variant: %s" % detection_variant)
    lines.append("")
    lines.append("  %-28s %-8s %s" % ("VARIANT", "RESULT", "EVIDENCE"))

    hits = 0
    for record in results:
        if record["hit"]:
            hits += 1
            status = "hit"
            evidence = repr(record.get("output"))
        elif record.get("error"):
            status = "error"
            evidence = record["error"]
        else:
            status = "miss"
            evidence = "expected %s, got %r" % (
                record.get("match"),
                record.get("output"),
            )
        lines.append("  %-28s %-8s %s" % (record["name"], status, evidence))

    lines.append("")
    lines.append("  %i/%i variants confirmed" % (hits, len(results)))
    return "\n".join(lines)


def format_catalogue():
    """Render the ``--list-variants`` catalogue."""

    lines = ["Tplmap payload variant catalogue", ""]
    for engine in ENGINES:
        variants = build_variants(engine)
        lines.append("%s (%i variants)" % (engine.capitalize(), len(variants)))
        for variant in variants:
            lines.append("  - %-28s %s" % (variant["name"], variant["description"]))
            lines.append("      code: %s" % variant["code"])
            lines.append(
                "      %s -> %r" % (variant["match"], variant["expected"])
            )
        lines.append("")
    return "\n".join(lines)
