// The generated client against the running users service (#6): the same
// binary cancho-web's own e2e suite runs, and the same document clientgen
// read -- one happy path and one `problem+json` refusal, typed both ways.
//
//   CANCHO=... WEB_DIR=... node tests/client_e2e.mjs
//
// * builds the users service with cancho-web's scripts/build.sh (the pinned
//   compiler and the locked packages, exactly as that repo's CI does);
// * compiles examples/users/ts/client.ts with tsc --strict and imports it;
// * createUser returns a typed User (the interface says `id`), getUser too;
// * a body that breaks the schema is a ProblemError with `errors`, each
//   carrying `pointer`/`code`/`detail` -- the typed error the caller must
//   handle, not a stringly catch.
import { execFileSync, spawn } from "node:child_process";
import net from "node:net";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const ROOT = path.resolve(import.meta.dirname, "..");
const CANCHO = process.env.CANCHO ?? "cancho";
const WEB_DIR = process.env.WEB_DIR ?? path.join(ROOT, "..", "cancho-web");

function freePort() {
  return new Promise((ok, bad) => {
    const s = net.createServer();
    s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => ok(p)); });
    s.on("error", bad);
  });
}

function fail(msg) {
  console.error("client_e2e: " + msg);
  process.exit(1);
}

// Build the users service, if not already built (CI of cancho-web does the
// same through scripts/build.sh).
const bin = process.env.USERS_BIN ?? path.join(ROOT, "build", "users");
if (!fs.existsSync(bin)) {
  try {
    execFileSync(path.join(WEB_DIR, "scripts", "build.sh"),
      [path.join(WEB_DIR, "examples", "users", "users.cho"), bin],
      { stdio: "inherit", env: { ...process.env, CANCHO } });
  } catch {
    fail("could not build the users service (is cancho-web checked out beside this repo?)");
  }
}

// Compile the committed client: tsc --strict is part of the gate.
const outDir = fs.mkdtempSync(path.join(os.tmpdir(), "clientgen-"));
execFileSync("npx", ["-y", "-p", "typescript", "tsc", "--strict",
  "--target", "es2022", "--lib", "es2022,dom", "--module", "nodenext",
  "--moduleResolution", "nodenext", "--outDir", outDir,
  path.join(ROOT, "examples", "users", "ts", "client.ts")], { stdio: "inherit" });

const port = await freePort();
const proc = spawn(bin, [String(port)], { stdio: ["ignore", "inherit", "pipe"] });
const line = await new Promise(r => proc.stderr.once("data", r));
if (!line.toString().includes(`listening on ${port}`)) fail("the service did not start: " + line);

let failures = 0;
const check = (ok, what) => {
  console.log((ok ? "ok  " : "FAIL ") + what);
  if (!ok) failures += 1;
};

try {
  const client = await import(path.join(outDir, "client.js"));
  client.setBase(`http://127.0.0.1:${port}`);

  // One happy path, typed: create, then read back through the typed client.
  const created = await client.createUser({ name: "Ada Lovelace", email: "ada@example.org", age: 36, role: "admin", tags: ["math"] });
  check(typeof created.id === "number" && created.name === "Ada Lovelace", "createUser returns a typed User (id: number)");

  const page = await client.listUsers({ limit: 1 });
  check(page.total === 1 && page.items[0].name === "Ada Lovelace", "listUsers returns a typed Page");

  const got = await client.getUser(created.id);
  check(got.email === "ada@example.org", "getUser returns the typed User");

  // One refusal, typed: a body that breaks the schema is ProblemError with
  // `errors`, each with pointer/code/detail -- RFC 9457, the typed way.
  let problem = null;
  try {
    await client.createUser({ name: "", age: 151 });
  } catch (e) {
    problem = e;
  }
  check(problem instanceof client.ProblemError, "a refused body throws ProblemError");
  check(problem?.problem?.status === 422, "the problem is the 422");
  check(Array.isArray(problem?.problem?.errors) && problem.problem.errors.length === 2, "every error at once (2 for this body)");
  check(problem?.problem?.errors?.every?.(d => "pointer" in d && "code" in d && "detail" in d), "each error carries pointer/code/detail");

  const gone = await client.deleteUser(created.id);
  check(gone === undefined, "deleteUser returns the 204 as void");
} catch (e) {
  fail(String(e));
} finally {
  proc.kill();
}

if (failures) fail(failures + " check(s) failed");
console.log("client_e2e: the generated client agrees with the running service");
