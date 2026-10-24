#!/usr/bin/env python3
"""The generated Python client against the running users service (#8): the
same binary cancho-web's own e2e suite runs, and the same document clientgen
read -- one happy path and one `problem+json` refusal, typed both ways.

    CANCHO=... WEB_DIR=... python3 tests/client_e2e.py

* builds the users service with cancho-web's scripts/build.sh (the pinned
  compiler and the locked packages, exactly as that repo's CI does);
* imports examples/users/py/client.py (already mypy --strict clean);
* createUser returns a User dataclass, listUsers a Page dataclass (a response is the dataclass it declares,
  not a dict under an annotation);
* a body that is not what the document says -- a field of the wrong kind, a required field missing -- is a
  ResponseError naming where, what was expected and what arrived (a small local server answers those);
* a body that breaks the schema is a ProblemError with the problem on
  `.problem` and the 422's `errors` (pointer/code/detail each) -- the typed
  error the caller must handle, not a stringly catch.
"""
import http.server
import importlib.util
import os
import socket
import subprocess
import sys
import tempfile
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANCHO = os.environ.get("CANCHO", "cancho")
WEB_DIR = os.environ.get("WEB_DIR", os.path.join(ROOT, "..", "cancho-web"))


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def fail(msg):
    print("client_e2e: " + msg, file=sys.stderr)
    sys.exit(1)


bin_path = os.environ.get("USERS_BIN", os.path.join(ROOT, "build", "users"))
if not os.path.exists(bin_path):
    try:
        subprocess.run([os.path.join(WEB_DIR, "scripts", "build.sh"),
                        os.path.join(WEB_DIR, "examples", "users", "users.cho"), bin_path],
                       check=True, env={**os.environ, "CANCHO": CANCHO})
    except Exception:
        fail("could not build the users service (is cancho-web checked out beside this repo?)")

port = free_port()
proc = subprocess.Popen([bin_path, str(port)], stderr=subprocess.PIPE)
line = proc.stderr.readline().decode().strip()
if f"listening on {port}" not in line:
    fail("the service did not start: " + line)

failures = 0


def check(ok, what):
    global failures
    print(("ok  " if ok else "FAIL ") + what)
    if not ok:
        failures += 1


try:
    spec = importlib.util.spec_from_file_location("client", os.path.join(ROOT, "examples", "users", "py", "client.py"))
    client_mod = importlib.util.module_from_spec(spec)
    sys.modules["client"] = client_mod
    spec.loader.exec_module(client_mod)
    c = client_mod.Client(f"http://127.0.0.1:{port}")

    # One happy path, typed.
    created = c.createUser(body=client_mod.NewUser(name="Ada Lovelace", email="ada@example.org", age=36, role="admin"))
    check(isinstance(created, client_mod.User) and created.name == "Ada Lovelace", "createUser returns a User dataclass")

    page = c.listUsers(limit=1)
    check(isinstance(page, client_mod.Page) and page.total == 1 and page.items[0]["name"] == "Ada Lovelace",
          "listUsers returns a Page dataclass")

    got = c.getUser(created.id)
    check(isinstance(got, client_mod.User) and got.email == "ada@example.org" and got == created,
          "getUser returns a User dataclass equal to the one created")

    # One refusal, typed.
    try:
        c.createUser(body=client_mod.NewUser(name="", age=151))
        problem = None
    except client_mod.ProblemError as e:
        problem = e
    check(problem is not None, "a refused body raises ProblemError")
    check(problem is not None and problem.problem.status == 422, "the problem is the 422")
    check(problem is not None and len(problem.problem.errors or []) == 2, "every error at once (2 for this body)")
    errs = (problem.problem.errors or []) if problem else []
    check(all("pointer" in e and "code" in e and "detail" in e for e in errs), "each error carries pointer/code/detail")

    gone = c.deleteUser(created.id)
    check(gone is None, "deleteUser returns the 204 as None")

    # A response that is not what the document says: a ResponseError, never a guess.
    def answer_with(body: bytes):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server

    def refused(body: bytes, call):
        server = answer_with(body)
        try:
            call(client_mod.Client(f"http://127.0.0.1:{server.server_address[1]}"))
            return None
        except client_mod.ResponseError as e:
            return e
        finally:
            server.shutdown()

    e = refused(b'{"id": "7", "name": "x"}', lambda cl: cl.getUser(7))
    check(e is not None and (e.where, e.expected, e.got) == ("$.id", "an integer", "a string"),
          "a field of the wrong kind is a ResponseError that names where, what was expected and what arrived")
    e = refused(b'{"name": "x"}', lambda cl: cl.getUser(7))
    check(e is not None and e.where == "$.id", "a required field that is missing is a ResponseError")
    e = refused(b'{"total": true, "items": []}', lambda cl: cl.listUsers())
    check(e is not None and (e.where, e.got) == ("$.total", "a boolean"), "a boolean is not an integer")
    e = refused(b'{"total": 1, "items": [3]}', lambda cl: cl.listUsers())
    check(e is not None and e.where == "$.items[0]", "the path into an array names the index")
    ok_page = answer_with(b'{"total": 1, "items": [{"id": 1}], "extra": 5}')
    try:
        extra = client_mod.Client(f"http://127.0.0.1:{ok_page.server_address[1]}").listUsers()
        check(extra.total == 1, "a member the document does not name is ignored, not refused")
    finally:
        ok_page.shutdown()
except Exception as e:
    fail(f"{type(e).__name__}: {e}")
finally:
    proc.kill()
    proc.wait()

if failures:
    fail(f"{failures} check(s) failed")
print("client_e2e: the generated Python client agrees with the running service")
