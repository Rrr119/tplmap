"""Tests for the Jinja2/Twig/FreeMarker payload variants and local ranges.

These tests are self-contained: they spawn the real engine ranges under
``ranges/`` (Jinja2 in-process library, a bundled/static PHP with Twig and a
JVM with FreeMarker when those runtimes are available under ``.runtimes``).

Run from the repository root:

    python3 -m unittest tests.test_engine_variants -v

Runtime-free tests (catalogue, scoring, CLI help) always run; the live
range tests are skipped when a runtime is unavailable.
"""

import os
import re
import subprocess
import sys
import unittest
import urllib.parse

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS_DIR)
sys.path.insert(0, ROOT)
sys.path.insert(1, TESTS_DIR)

from core.channel import Channel  # noqa: E402
from core.checks import detect_template_injection  # noqa: E402
from core.variants import (  # noqa: E402
    ENGINES,
    build_variants,
    format_catalogue,
    score_variant,
)
from plugins.engines.freemarker import Freemarker  # noqa: E402
from plugins.engines.jinja2 import Jinja2  # noqa: E402
from plugins.engines.twig import Twig  # noqa: E402
from ranges import harness  # noqa: E402
from benchmarks.run_comparison import SCENARIOS, run_case, run_comparison  # noqa: E402


PLUGIN_CLASSES = {
    "jinja2": Jinja2,
    "twig": Twig,
    "freemarker": Freemarker,
}

ENGINE_LABELS = {
    "jinja2": "Jinja2",
    "twig": "Twig",
    "freemarker": "Freemarker",
}


def detect_on(url, engine, payload_variants=False, level=0, clevel=0):
    channel = Channel(
        {
            "url": url,
            "force_level": [level, clevel],
            "injection_tag": "*",
            "technique": "R",
            **({"payload_variants": True} if payload_variants else {}),
        }
    )
    plugin = detect_template_injection(channel, plugins=[PLUGIN_CLASSES[engine]])
    return channel, plugin


class VariantCatalogueTests(unittest.TestCase):
    """The variant catalogue itself must be complete and self-consistent."""

    def test_three_engines_listed(self):
        self.assertEqual(set(ENGINES), {"jinja2", "twig", "freemarker"})
        catalogue = format_catalogue()
        for label in ("Jinja2", "Twig", "Freemarker"):
            self.assertIn(label, catalogue)

    def test_variants_have_unique_complete_fields(self):
        for engine in ENGINES:
            variants = build_variants(engine)
            self.assertGreaterEqual(len(variants), 7, engine)
            names = [variant["name"] for variant in variants]
            self.assertEqual(len(names), len(set(names)), "duplicate variant names")
            for variant in variants:
                self.assertTrue(variant["name"])
                self.assertTrue(variant["description"])
                self.assertTrue(variant["code"])
                self.assertIn(variant["match"], ("equals", "contains", "regex"))
                self.assertNotEqual(variant["expected"], "")

    def test_random_builds_are_independent(self):
        first = build_variants("jinja2")
        second = build_variants("jinja2")
        self.assertEqual(len(first), len(second))
        # Random operands should differ between builds with overwhelming odds.
        self.assertNotEqual(
            [v["expected"] for v in first if v["name"] == "math_random_mul"],
            [v["expected"] for v in second if v["name"] == "math_random_mul"],
        )

    def test_score_variant_modes(self):
        self.assertTrue(score_variant({"match": "equals", "expected": "49"}, "49"))
        self.assertFalse(score_variant({"match": "equals", "expected": "49"}, " 49 "))
        self.assertTrue(
            score_variant({"match": "contains", "expected": "abc"}, "xxabcyy")
        )
        self.assertTrue(
            score_variant({"match": "regex", "expected": r"^\w+$"}, "posix")
        )
        self.assertFalse(
            score_variant({"match": "regex", "expected": r"^\d+$"}, "nope")
        )
        self.assertFalse(score_variant({"match": "equals", "expected": "x"}, None))

    @unittest.skipUnless(harness.jinja2_available(), "jinja2 library not installed")
    def test_jinja2_variant_expectations_are_true(self):
        # Evaluate every Jinja2 variant through the exact engine render wrapper.
        import jinja2

        env = jinja2.Environment(line_statement_prefix="#")
        for variant in build_variants("jinja2"):
            output = env.from_string("{{ " + variant["code"] + " }}").render()
            self.assertTrue(
                score_variant(variant, output.strip()),
                "Jinja2 variant %s yielded %r (expected %r)"
                % (variant["name"], output, variant["expected"]),
            )


class CliCompatibilityTests(unittest.TestCase):
    def test_help_keeps_existing_options_and_adds_variants(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "tplmap.py"), "-h"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0)
        for existing in ("-u URL", "--level", "-e ENGINE", "-t TECHNIQUE", "--data",
                         "--os-cmd", "--download", "--force-level", "--injection-tag"):
            self.assertIn(existing, output, "missing legacy option %s" % existing)
        self.assertIn("--variants", output)
        self.assertIn("--list-variants", output)

    def test_list_variants_cli(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "tplmap.py"), "--list-variants"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("math_7x7", proc.stdout)
        self.assertIn("interpolation_7x7", proc.stdout)
        self.assertIn("Freemarker", proc.stdout)


PROCS = {}


def setUpModule():
    info = harness.availability()
    for engine in ENGINES:
        if not info.get(engine):
            continue
        try:
            PROCS[engine] = harness.SPAWNERS[engine]().start()
        except Exception as error:  # pragma: no cover - environment dependent
            sys.stderr.write("range %s failed to start: %s\n" % (engine, error))


def tearDownModule():
    for process in PROCS.values():
        process.stop()


def _plain_url(engine):
    query = urllib.parse.urlencode({"tpl": "%s"})
    return "%s/reflect/%s?%s&inj=*" % (PROCS[engine].base_url, engine, query)


class LiveRangeDetectionTests(unittest.TestCase):
    def _require_ranges(self):
        if not PROCS:
            self.skipTest("no local template range runtimes are available")

    def test_plain_detection_all_engines(self):
        self._require_ranges()
        for engine in ENGINES:
            if engine not in PROCS:
                self.skipTest("%s runtime unavailable" % engine)
            channel, _plugin = detect_on(_plain_url(engine), engine)
            self.assertEqual(channel.data.get("engine"), engine, engine)

    def test_every_non_filter_context_case_is_detected(self):
        self._require_ranges()
        for engine in ENGINES:
            if engine not in PROCS:
                continue
            for scenario in SCENARIOS[engine]:
                if scenario[4]:
                    continue
                with self.subTest(engine=engine, case=scenario[0]):
                    result = run_case(PROCS[engine].base_url, engine, scenario)
                    self.assertTrue(
                        result["baseline_detected"],
                        "baseline missed %s/%s" % (engine, scenario[0]),
                    )
                    self.assertTrue(result["variants_detected"])

    def test_all_variants_hit_on_plain_context(self):
        self._require_ranges()
        from core.variants import run_suite

        for engine in ENGINES:
            if engine not in PROCS:
                self.skipTest("%s runtime unavailable" % engine)
            _channel, plugin = detect_on(_plain_url(engine), engine, True)
            records = run_suite(plugin)
            misses = [r["name"] for r in records if not r["hit"]]
            self.assertEqual(misses, [], "%s variant misses: %s" % (engine, misses))
            self.assertEqual(len(records), 7)

    def test_filter_cases_need_variant_rescue(self):
        self._require_ranges()
        for engine in ENGINES:
            if engine not in PROCS:
                continue
            for scenario in SCENARIOS[engine]:
                if not scenario[4]:
                    continue
                with self.subTest(engine=engine, case=scenario[0]):
                    result = run_case(PROCS[engine].base_url, engine, scenario)
                    self.assertFalse(
                        result["baseline_detected"],
                        "test setup wrong: baseline should miss %s" % scenario[0],
                    )
                    self.assertTrue(
                        result["variants_detected"],
                        "variants did not rescue %s" % scenario[0],
                    )
                    self.assertIsNotNone(result["rescued_by_variant"])

    def test_cli_scan_with_variants(self):
        self._require_ranges()
        ansi = re.compile(r"\x1b\[[0-9;]*m")
        for engine in ENGINES:
            if engine not in PROCS:
                self.skipTest("%s runtime unavailable" % engine)
            proc = subprocess.run(
                [
                    sys.executable,
                    os.path.join(ROOT, "tplmap.py"),
                    "-u",
                    _plain_url(engine),
                    "-e",
                    ENGINE_LABELS[engine],
                    "-t",
                    "R",
                    "--variants",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=120,
            )
            output = ansi.sub("", proc.stdout + proc.stderr)
            with self.subTest(engine=engine):
                self.assertEqual(proc.returncode, 0)
                self.assertIn("Engine: %s" % ENGINE_LABELS[engine], output)
                self.assertIn("7/7 variants confirmed", output)

    def test_cli_filter_rescue_jinja2(self):
        self._require_ranges()
        if "jinja2" not in PROCS:
            self.skipTest("jinja2 runtime unavailable")
        query = urllib.parse.urlencode({"tpl": "%s"})
        url = "%s/reflect/jinja2/filter_canonical?%s&inj=*" % (
            PROCS["jinja2"].base_url,
            query,
        )
        proc = subprocess.run(
            [
                sys.executable,
                os.path.join(ROOT, "tplmap.py"),
                "-u",
                url,
                "-e",
                "Jinja2",
                "--variants",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = re.sub(r"\x1b\[[0-9;]*m", "", proc.stdout + proc.stderr)
        self.assertIn("Engine: Jinja2", output)
        self.assertIn("detection confirmed by fallback variant", output)


class ComparisonReportTests(unittest.TestCase):
    def test_comparison_rates_and_markdown(self):
        report = run_comparison(run_cli=False)

        for engine in ENGINES:
            data = report["engines"].get(engine, {})
            if data.get("skipped"):
                self.skipTest("%s range unavailable" % engine)
            self.assertEqual(data["total_cases"], 8)
            self.assertEqual(data["baseline_detected"], 6)
            self.assertLess(data["baseline_rate"], data["variants_rate"])
            self.assertEqual(data["variants_detected"], 8)
            self.assertEqual(data["variants_rate"], 1.0)
            self.assertEqual(len(data["gained"]), 2)
            for variant, stat in data["variant_hits"].items():
                self.assertEqual(stat["hit_rate"], 1.0, variant)

        markdown = __import__(
            "benchmarks.run_comparison", fromlist=["render_markdown"]
        ).render_markdown(report)
        for token in ("Detection rate by range", "Jinja2", "Twig", "Freemarker", "100%"):
            self.assertIn(token, markdown)


if __name__ == "__main__":
    unittest.main(verbosity=2)
