#!/usr/bin/env python3
"""The generated Python client against the running users service (#8): the
same binary cancho-web's own e2e suite runs, and the same document clientgen
read -- one happy path and one `problem+json` refusal, typed both ways.

    CANCHO=... WEB_DIR=... python3 tests/client_e2e.py

* builds the users service with cancho-web's scripts/build.sh (the pinned
  compiler and the locked packages, exactly as that repo's CI does);
* imports examples/users/py/client.py (already mypy --strict clean);
* createUser returns a typed User, listUsers a typed Page;
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
    check(isinstance(created, dict) and created["name"] == "Ada Lovelace", "createUser returns the typed User")

    page = c.listUsers(limit=1)
    check(page["total"] == 1 and page["items"][0]["name"] == "Ada Lovelace", "listUsers returns the typed Page")

    got = c.getUser(created["id"])
    check(got["email"] == "ada@example.org", "getUser returns the typed User")

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

    gone = c.deleteUser(created["id"])
    check(gone is None, "deleteUser returns the 204 as None")
except Exception as e:
    fail(f"{type(e).__name__}: {e}")
finally:
    proc.kill()
    proc.wait()

if failures:
    fail(f"{failures} check(s) failed")
print("client_e2e: the generated Python client agrees with the running service")
