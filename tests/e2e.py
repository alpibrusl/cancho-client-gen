#!/usr/bin/env python3
"""End-to-end tests of `clientgen`: the reader (#3) and the model (#4), over
the byte-verified document.

    CANCHO=/path/to/cancho   (default: cancho on PATH)
    BIN=build/clientgen      (skip the build)

The first test input is cancho-web's `examples/users/openapi.json`, pinned
byte for byte by that repository's e2e suite. `--check` answers whether a
client can come from the document (the gate's first half, issue #6); `--model`
builds the model -- operations, parameters, bodies, responses, components
with `$ref` resolved to a name (issue #4) -- and prints it. Every refusal is
exercised with a file that fails in exactly one way -- pgen's discipline:
nothing is written for an invalid document.
"""
import hashlib
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANCHO = os.environ.get("CANCHO", "cancho")
BIN = os.environ.get("BIN")
USERS = os.path.join(ROOT, "examples", "users", "openapi.json")

USERS_MODEL = """get /health -> health (0 parameters, body none, 1 responses: 200=object )
get /users -> listUsers (2 parameters, body none, 2 responses: 200=Page 422=Problem )
post /users -> createUser (0 parameters, body NewUser, 5 responses: 201=User 400=Problem 415=Problem 422=Problem 503=Problem )
get /users/{id} -> getUser (1 parameters, body none, 3 responses: 200=User 404=Problem 422=Problem )
delete /users/{id} -> deleteUser (1 parameters, body none, 3 responses: 204=none 404=Problem 422=Problem )
component NewUser: object
component User: object
component Page: object
component Problem: object
"""


def build():
    subprocess.run([CANCHO, "build", "--std", "--backend", "cranelift",
                    os.path.join(ROOT, "src", "clientgen.cho"),
                    os.path.join(ROOT, "src", "model.cho"),
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


def doc(paths, components=None):
    body = '{"openapi":"3.1.0","info":{"title":"t","version":"1"},"paths":%s' % paths
    if components is not None:
        body += ',"components":%s' % components
    return body + "}"


class Reader(unittest.TestCase):
    def setUp(self):
        global BIN
        if BIN is None:
            os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
            BIN = build()

    def test_users_document(self):
        """The byte-verified document: 5 operations, 4 named components."""
        out, err, st = run(USERS, "--check")
        self.assertEqual(st, 0)
        self.assertEqual(out, "ok 5 operations, 4 components\n")
        self.assertEqual(err, "")

    def test_users_model(self):
        """The model of the byte-verified document: document order, $ref resolved to a name."""
        out, err, st = run(USERS, "--model")
        self.assertEqual(st, 0)
        self.assertEqual(out, USERS_MODEL)
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

    def test_model_refusals(self):
        """The model's own refusals (issue #4), each named."""
        cases = [
            (doc('{"/a":{"get":{"responses":{}}}}'), "an operation has no `operationId`"),
            (doc('{"/a":{"get":{"operationId":"x"}}}'), "an operation has no `responses`"),
            (doc('{"/a":{"get":{"operationId":"x","responses":{},"parameters":[{"name":"n","in":"query"}]}}}'), "a parameter has no `schema`"),
            (doc('{"/a":{"get":{"operationId":"x","responses":{},"parameters":[{"name":"n","in":"body","schema":{"type":"string"}}]}}}'), "a parameter's `in` is not path, query or header"),
            (doc('{"/a":{"get":{"operationId":"x","responses":{"200":{"description":"d","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Missing"}}}}}}}}'), "a `$ref` points nowhere"),
            (doc('{"/a":{"get":{"operationId":"x","responses":{"200":{"$ref":"#/components/responses/Nope"}}}}}', '{"responses":{}}'), "a `$ref` points nowhere"),
            (doc('{"/a":{"get":{"operationId":"x","responses":{"ok":{"description":"d"}}}}}'), "a response key is not a status"),
            (doc('{"/a":{"get":{"operationId":"x","responses":{"200":{"description":"d","content":{"application/json":{"schema":{"type":"mime"}}}}}}}}'), "a schema is of no kind the model names"),
        ]
        for text, why in cases:
            with self.subTest(why=why):
                path = write("bad.json", text)
                out, err, st = run(path, "--model")
                self.assertEqual(st, 1)
                self.assertEqual(err, f"clientgen: {path}: {why}\n")
                self.assertEqual(out, "")

    def test_path_level_parameters_inherited(self):
        """A path item's `parameters` apply to every operation under it (issue #4)."""
        text = doc('{"/a":{"parameters":[{"name":"id","in":"path","required":true,"schema":{"type":"integer"}}],'
                   '"get":{"operationId":"x","responses":{}},"delete":{"operationId":"y","responses":{}}}}')
        path = write("params.json", text)
        out, err, st = run(path, "--model")
        self.assertEqual(st, 0)
        self.assertEqual(out, "get /a -> x (1 parameters, body none, 0 responses: )\n"
                              "delete /a -> y (1 parameters, body none, 0 responses: )\n")

    def test_response_ref_resolves(self):
        """A response that is a `$ref` to a named response component resolves to its body."""
        text = doc('{"/a":{"get":{"operationId":"x","responses":{"200":{"$ref":"#/components/responses/Ok"}}}}}',
                   '{"responses":{"Ok":{"description":"d","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Thing"}}}}},'
                   '"schemas":{"Thing":{"type":"object"}}}')
        path = write("resp_ref.json", text)
        out, err, st = run(path, "--model")
        self.assertEqual(st, 0)
        self.assertIn("responses: 200=Thing", out)
        self.assertIn("component Thing: object", out)

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
        """The smallest document a client can come from: one operation, no components."""
        path = write("minimal.json", doc('{"/a":{"get":{"operationId":"x","responses":{}}}}'))
        out, err, st = run(path, "--check")
        self.assertEqual(st, 0)
        self.assertEqual(out, "ok 1 operations, 0 components\n")

    def test_no_check_writes_nothing(self):
        """Without a target, plain mode refuses rather than pretending to generate."""
        out, err, st = run(USERS)
        self.assertEqual(st, 1)
        self.assertIn("the TypeScript and Go writers are built", err)
        self.assertIn("the Python writer is not", err)
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
        self.assertEqual(err, "usage: clientgen <openapi.json> [--check | --model | --typescript -o <file> | --go -o <file>]\n")

    def test_typescript_client(self):
        """The generated client is the committed one, byte for byte (the gate's shape)."""
        out_path = os.path.join(ROOT, "build", "client.ts")
        out, err, st = run(USERS, "--typescript", "-o", out_path)
        self.assertEqual(st, 0)
        self.assertEqual(out, "")
        self.assertEqual(err, "")
        with open(out_path, "rb") as f:
            with open(os.path.join(ROOT, "examples", "users", "ts", "client.ts"), "rb") as g:
                self.assertEqual(f.read(), g.read(), "examples/users/ts/client.ts is stale: regenerate it")

    def test_go_client(self):
        """The generated Go client is the committed one, byte for byte."""
        out_path = os.path.join(ROOT, "build", "client.go")
        out, err, st = run(USERS, "--go", "-o", out_path)
        self.assertEqual(st, 0)
        self.assertEqual(err, "")
        with open(out_path, "rb") as f:
            with open(os.path.join(ROOT, "examples", "users", "go", "client.go"), "rb") as g:
                self.assertEqual(f.read(), g.read(), "examples/users/go/client.go is stale: regenerate it")

    def test_go_build(self):
        """The committed Go client builds and vets (the issue's bar)."""
        godir = os.path.join(ROOT, "examples", "users", "go")
        if not os.path.exists(os.path.join(godir, "client.go")):
            self.skipTest("committed Go client not present")
        go = os.environ.get("GO", "go")
        for check in ([go, "build", "./..."], [go, "vet", "./..."]):
            p = subprocess.run(check, cwd=godir, capture_output=True, text=True, timeout=300)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_typescript_deterministic(self):
        """Same document, same bytes: two runs agree."""
        one = os.path.join(ROOT, "build", "one.ts")
        two = os.path.join(ROOT, "build", "two.ts")
        run(USERS, "--typescript", "-o", one)
        run(USERS, "--typescript", "-o", two)
        with open(one, "rb") as f, open(two, "rb") as g:
            self.assertEqual(f.read(), g.read())

    def test_typescript_strict(self):
        """The generated client compiles under `tsc --strict` (the issue's bar)."""
        out_path = os.path.join(ROOT, "examples", "users", "ts", "client.ts")
        if not os.path.exists(out_path):
            self.skipTest("committed client not present")
        tsc = subprocess.run(["npx", "-y", "-p", "typescript", "tsc", "--strict", "--noEmit",
                             "--target", "es2022", "--lib", "es2022,dom", out_path],
                             capture_output=True, text=True, timeout=300)
        self.assertEqual(tsc.returncode, 0, tsc.stdout + tsc.stderr)

    def test_users_document_is_the_pinned_one(self):
        """The test input is the byte-verified document cancho-web's e2e pins."""
        with open(USERS, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(),
                             "cf61a8f0e99edd488fc56622e007742ba30b9c37e9c9cd9788e5b16919f630eb")


if __name__ == "__main__":
    unittest.main()
