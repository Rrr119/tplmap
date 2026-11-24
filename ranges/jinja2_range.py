#!/usr/bin/env python3
"""Local Jinja2 SSTI range for tplmap detection benchmarks.

Contract mirrors tests/env_py_tests/webserver.py:

    GET /reflect/jinja2?tpl=<template with %%s>&inj=<injection>

The server replaces the literal ``%%s`` placeholder in ``tpl`` with the
``inj`` value and renders the result with a real Jinja2 environment.

Paths containing ``filter_canonical`` enable a tiny denylist filter that
blocks the stock canonical probe (which contains a tuple and therefore
commas), while equivalent comma-free payload variants still evaluate.
"""

import argparse
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import jinja2


ENV = jinja2.Environment(line_statement_prefix="#")

# filter_canonical blocks the stock test_render "(n1,n2*n3)" via its commas.
# filter_secondary blocks the multiplication operator, leaving the tilde /
# upper / join variants as the only way through.
FILTERS = {
    "filter_canonical": (",",),
    "filter_secondary": ("*",),
}


def render_template(template_source, injection):
    source = template_source.replace("%s", injection)
    return ENV.from_string(source).render()


class Handler(BaseHTTPRequestHandler):
    server_version = "TplmapJinja2Range/1.0"

    def log_message(self, fmt, *args):  # quiet by default
        if getattr(self.server, "verbose", False):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, body, status=200, content_type="text/plain; charset=utf-8"):
        data = body.encode("utf-8", "replace") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)

        if parsed.path.rstrip("/") == "/health":
            self._send("ok")
            return

        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        template_source = query.get("tpl", ["%s"])[0] or "%s"
        injection = query.get("inj", [""])[0]

        for filter_name, blocked_tokens in FILTERS.items():
            if filter_name not in parsed.path:
                continue
            for token in blocked_tokens:
                if token in injection:
                    self._send("REQUEST BLOCKED BY RANGE FILTER")
                    return

        try:
            self._send(render_template(template_source, injection))
        except Exception:
            # Broken templates simply render nothing, like the PHP/Java ranges.
            self._send("")


def main():
    parser = argparse.ArgumentParser(description="Local Jinja2 SSTI range")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=15011)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    httpd.verbose = args.verbose
    print("jinja2 range listening on http://%s:%i" % (args.host, args.port), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
