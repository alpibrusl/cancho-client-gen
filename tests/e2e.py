#!/usr/bin/env python3
"""End-to-end tests of `clientgen`'s reader, over the byte-verified document.

    CANCHO=/path/to/cancho   (default: cancho on PATH)
    BIN=build/clientgen      (skip the build)

The first test input is cancho-web's `examples/users/openapi.json`, pinned
byte for byte by that repository's e2e suite: `clientgen --check` reads it
over `std.json`'s tape and must find the three paths, the five operations and
the two component groups the document has. Every refusal is exercised with a
file that fails in exactly one way -- pgen's discipline: nothing is written
for an invalid document, and this file is the gate's `--check` half (issue #6
builds the committed-output half on it).
"""
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANCHO = os.environ.get("CANCHO", "cancho")
BIN = os.environ.get("BIN")
USERS = os.path.join(ROOT, "examples", "users", "openapi.json")


def build():
    subprocess.run([CANCHO, "build", "--std", "--backend", "cranelift",
                    os.path.join(ROOT, "src", "clientgen.cho"),
                    "-o", os.path.join(ROOT, "build", "clientgen")], check=True)
    return os.path.join(ROOT, "build", "clientgen")


def run(*args):
    p = subprocess.run([BIN, *args], capture_output=True, text=True, timeout=60)
    return p.stdout, p.stderr, p.returncode


def write(name, text):
    path = os.path.join(ROOT, "build", name)
    with open(path, "w") as f:
        f.write(text)
    return path


class Reader(unittest.TestCase):
    def setUp(self):
        global BIN
        if BIN is None:
            os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
            BIN = build()

    def test_users_document(self):
        """The byte-verified document: 3 paths, 5 operations, 2 component groups."""
        out, err, st = run(USERS, "--check")
        self.assertEqual(st, 0)
        self.assertEqual(out, "ok 3 paths, 5 operations, 2 components\n")
        self.assertEqual(err, "")

    def test_valid_json_not_a_document(self):
        """Valid JSON that is not an OpenAPI 3.1 document is refused, not parsed past."""
        for text, why in [
            ('{"nope":1}', "`openapi` is missing or not a string"),
            ('{"openapi":2,"info":{"title":"t","version":"1"},"paths":{}}', "`openapi` is missing or not a string"),
            ('{"openapi":"3.0.0","info":{"title":"t","version":"1"},"paths":{}}', "`openapi` is not 3.1"),
            ('{"openapi":"3.1.0","paths":{}}', "`info` is missing or not an object"),
            ('{"openapi":"3.1.0","info":{"version":"1"},"paths":{}}', "`info.title` is missing or not a string"),
            ('{"openapi":"3.1.0","info":{"title":"t"},"paths":{}}', "`info.version` is missing or not a string"),
            ('{"openapi":"3.1.0","info":{"title":"t","version":"1"}}', "`paths` is missing or not an object"),
            ('{"openapi":"3.1.0","info":{"title":"t","version":"1"},"paths":{"/a":7}}', "a path item is not an object"),
            ('{"openapi":"3.1.0","info":{"title":"t","version":"1"},"paths":{},"components":[]}', "`components` is not an object"),
        ]:
            with self.subTest(why=why):
                path = write("bad.json", text)
                out, err, st = run(path, "--check")
                self.assertEqual(st, 1)
                self.assertEqual(err, f"clientgen: {path}: {why}\n")
                self.assertEqual(out, "")

    def test_not_json(self):
        """A file that is not valid JSON is refused with the parser's own error and where."""
        path = write("bad.json", '{"openapi": "3.1.0",,}')
        out, err, st = run(path, "--check")
        self.assertEqual(st, 1)
        self.assertEqual(err, f"clientgen: {path}: not valid JSON: unexpected character at byte 20\n")

    def test_truncated(self):
        path = write("bad.json", '{"openapi": "3.1.0", "info":')
        out, err, st = run(path, "--check")
        self.assertEqual(st, 1)
        self.assertEqual(err, f"clientgen: {path}: not valid JSON: unexpected end of input at byte 28\n")

    def test_empty_file(self):
        path = write("bad.json", "")
        out, err, st = run(path, "--check")
        self.assertEqual(st, 1)
        self.assertIn("not valid JSON", err)

    def test_minimal_document(self):
        """The smallest document a client can come from: one path, one operation."""
        path = write("minimal.json", '{"openapi":"3.1.0","info":{"title":"t","version":"1"},"paths":{"/a":{"get":{"responses":{}}}}}')
        out, err, st = run(path, "--check")
        self.assertEqual(st, 0)
        self.assertEqual(out, "ok 1 paths, 1 operations, 0 components\n")

    def test_parameters_is_not_an_operation(self):
        """A path-level `parameters` key is not an operation."""
        path = write("params.json", '{"openapi":"3.1.0","info":{"title":"t","version":"1"},"paths":{"/a":{"parameters":[{"name":"id","in":"path","required":true,"schema":{"type":"integer"}}],"get":{"responses":{}}}}}')
        out, err, st = run(path, "--check")
        self.assertEqual(st, 0)
        self.assertEqual(out, "ok 1 paths, 1 operations, 0 components\n")

    def test_no_check_writes_nothing(self):
        """Without a writer, plain mode refuses rather than pretending to generate."""
        out, err, st = run(USERS)
        self.assertEqual(st, 1)
        self.assertIn("the reader is built, the writers are not", err)
        self.assertEqual(out, "")

    def test_missing_file(self):
        out, err, st = run(os.path.join(ROOT, "no", "such", "document.json"), "--check")
        self.assertEqual(st, 1)
        self.assertEqual(err.split(": ", 2)[2], "cannot read that file\n")

    def test_dotdot_path(self):
        """A path with `..` is refused before the read, as pgen does: the file capability traps on it."""
        out, err, st = run("../examples/users/openapi.json", "--check")
        self.assertEqual(st, 1)
        self.assertEqual(err.split(": ", 2)[2], "a path with `..` in it is refused (the file capability traps on it); give the path without\n")

    def test_usage(self):
        out, err, st = run()
        self.assertEqual(st, 2)
        self.assertEqual(err, "usage: clientgen <openapi.json> [--check]\n")

    def test_users_document_is_the_pinned_one(self):
        """The test input is the byte-verified document cancho-web's e2e pins."""
        import hashlib
        with open(USERS, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(),
                             "cf61a8f0e99edd488fc56622e007742ba30b9c37e9c9cd9788e5b16919f630eb")


if __name__ == "__main__":
    print(__doc__.split("\n")[0] if __doc__ else "")
    unittest.main()
