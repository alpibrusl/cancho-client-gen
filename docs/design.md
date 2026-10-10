# cancho-client-gen: strictly typed clients from the byte-verified document

> **Status: all seven slices built (#3–#9, 2026-10-10)**: the reader, the model, the TypeScript, Go
> and Python targets, the gate, and the cancho client. The epic (#2) is complete; the open questions
> are in §10. This document is the design those slices were built against, written after the fact for the
> first five and before the fact for the last two — the cancho tradition is design before code, and the
> first five slices carried their design in the epic (#2) and its issues instead; this file makes it
> checked-in.

## 1. What it is, and is not

`pgen` (in [cancho-pg](https://github.com/alpibrusl/cancho-pg)) turns `queries.sql` into typed cancho
functions by asking the database. This turns `openapi.json` into typed clients by reading the
document. Same discipline on both sides of the analogy:

| | pgen | clientgen |
|---|---|---|
| input | a `.sql` file | an OpenAPI 3.1 document |
| the thing it asks | the server's `describe` | the document's own schema tree |
| what it refuses | a statement the server rejects | a document that does not model |
| output | typed cancho functions | typed client libraries (TS, Go, Python, cancho) |
| the gate | the generated module is committed; CI regenerates | the generated client is committed; CI regenerates and diffs |

It is not a schema validator (that is the producer's job — cancho-web's e2e and Schemathesis hold the
document on the server side), not a docs UI, and not a code generator for arbitrary schemas: it writes
what a client needs — operations, parameters, bodies, responses, named components — and refuses the
rest.

## 2. Why the document, not the declaration

The declaration is a running program and a second source of truth: a generator that read it would
have to run the service or re-read `.cho` source (cancho-web's design §9.9 rejected generated records
there for exactly this reason). The document is a file, already verified — cancho-web's e2e holds
what the service serves byte for byte against the checked-in `openapi.json` — and consuming it keeps
the tool useful for **any OpenAPI 3.1 producer**, not just cancho-web.

One contract, both directions: the server is held to the document by tests, the client is written
from the document by this tool, and the gate (#6) makes a disagreement between them a red build
rather than an integration break.

## 3. The shape of the tool

Three layers, one binary, `clientgen <document>`:

```
the file  --fs_read-->  the tape  --std.json-->  the model  --a writer-->  the client
         (#3, clientgen.cho)                    (#4, model.cho)          (#5 ts, #7 go, #8 python)
```

* **The reader (#3)** parses with `std.json`'s tape — no copy of the source, no foreign code — and
  walks the OpenAPI shape: `openapi` (3.1.x), `info.title`/`info.version`, `paths` (each item an
  object), `components`. Nine named refusals (`Refusal::RootNotObject` … `PathItemNotObject`), each
  saying what a client needs and where it is missing.
* **The model (#4)** reads what the writers write from: a `Method` and a `Where` enum, a `Schema`
  enum (`Ref` holding the component's *name* — the point of `$ref` resolution — alongside
  `Boolean/Integer/Number/String/Array/Box/Object`), a res struct per thing (`Operation`,
  `Parameter`, `Response`, `Field`, `Component`, `Doc`), in document order. All `res`, so the
  checker holds the tool to freeing the model; the writer consumes it as it prints.
* **The writers** share the discipline: one deterministic file per document (same document, same
  bytes), an aggregate type per component, a typed function per operation, `problem+json` as the
  typed error the caller must handle. Strictness is the point: a required parameter is a required
  argument; the error is thrown/returned, never in the success union.

## 4. The refusals (pgen's gate, before the gate)

Nothing is written for a document that does not model. Eighteen named refusals cover the reader's
nine and the model's nine (`OperationNoResponses`, `OperationIdMissing`, `ParameterNoSchema`,
`ParameterBadIn`, `ParameterBadRequired`, `RefNowhere`, `RefNotSchemas`, `ResponseBadStatus`,
`SchemaUnknownKind`). A `$ref` that points nowhere is an error when it is made — the schema names are
collected from the tape before anything is read, and a reference is checked against them as it is
resolved — not a best-effort inline and not a surprise in a generated client. A response that is a
`$ref` to a named response component (`422` in the users document) is followed to its
`application/problem+json` schema: the typed error is the document's own `Problem` component when it
names one, and the writers do not emit a duplicate.

## 5. The writers, decided

Two are built; the third (#8) follows the same decisions.

* **Types.** An `interface` (TS) or `struct` (Go) per `components.schemas` entry. Fields are
  exported/tagged: TS keeps the document's spelling with `?` for the optional; Go exports the field
  name and puts the document's spelling in the json tag, with `omitempty` exactly when the document
  does not require the field — strictness at the marshal boundary is the tag's to enforce. An inline
  object (until [cancho-web#16](https://github.com/alpibrusl/cancho-web/issues/16) names them) is
  written structurally, as the model kept it.
* **Operations.** Required path parameters are required arguments. Optional query parameters become
  one options argument (TS: `options?: { limit?: number }`; Go: a `*OpOptions` struct whose
  `query()` satisfies the runtime's `querier`). The body is typed by its schema (Go: a pointer, so
  a required body is distinguishable from an absent one). The return is the typed union of the
  **2xx** bodies (TS: a union; Go: the single 2xx type or `struct{}`); error responses are thrown
  or returned as the typed error, never in the success union. A `204` is void/the zero value.
* **The typed error.** TS: `ProblemError extends Error` carrying the Problem's fields and the 422's
  `errors` with `pointer`/`code`/`detail`. Go: `*ProblemError` implementing `error`. Python (#8):
  an exception class. The runtime checks the response's content type — `problem+json` is the typed
  error, no coercion, no stringly catch.
* **The runtime.** Small, per-target, in the file: a client with a settable base URL, the request
  builder, the decode. No dependency beyond the target's standard library (`fetch`, `net/http`;
  Python: `urllib.request`, no third-party package — a generated client that needs `pip install
  anything` has failed the point).

## 6. The gate (#6)

`scripts/check-client.sh` regenerates **every** committed client from the checked-in document and
diffs (`git diff --exit-code` in CI): a contract change without a regenerated client is a red build,
not an integration break. `tests/client_e2e.mjs` is the acceptance test of the whole: it builds the
users service with cancho-web's own `scripts/build.sh` (the same binary that repo's e2e runs), starts
it, compiles the committed TypeScript client under `tsc --strict`, and calls through it — happy
paths typed, the 422 as `ProblemError` with every error at once, each carrying
`pointer`/`code`/`detail`. Server and client cannot disagree silently; the last line it prints is
the repository's thesis.

## 7. What building it found

* **The model's `Schema::Object` had to grow fields** (#4 → #5): an interface is written from
  `properties` with per-field `required`; the model kept only the kind. `Field` carries the required
  flag itself, because OpenAPI lists `required` by name and the pair travels together.
* **`problem+json` was invisible to the first reader**: the users document's `422` is a `$ref` to a
  named response component whose content is `application/problem+json`, not `application/json`. The
  reader follows response `$ref`s and recognises both media types — the typed error is the document's
  own `Problem`, not an invented one.
* **Determinism bugs were found by printing the model** (`--model`): the lists were built
  front-first and the "reverse" was the identity (a `push` after a reverse is the original order).
  Document order is now tested on both writers and both clients.
* **Go taught the writers two rules the issue did not name**: field names must be exported for
  JSON to see them (the tag keeps the contract), and the runtime must be a *generator's* runtime —
  the first attempt returned the raw `*http.Response` while the functions promised `(User, error)`.
  The honest shape is a small generic `decode[T]` per file.
* **`--check`'s counts changed meaning** (#4): "3 paths" became "5 operations, 4 components" when
  the model arrived. The reader's shape walk and the model's counts are different questions; the
  gate cares about the second.

## 8. The Python target (#8), built as decided

Same model, same gate, third writer (`src/py.cho`, `clientgen <doc> --python -o <file>`):

* a `@dataclass` per component (frozen, `total=False` not used — the optional are `X | None = None`,
  so a required field is distinguishable from an absent one, which is the same strictness the Go
  pointer and the TS `?` give);
* a typed method per operation on a `Client` class: required path parameters positional, optional
  query parameters one keyword-only `options` argument (or, simpler and flatter: keyword arguments
  with the optionality in the signature — decided: keyword arguments, because Python has no struct
  literal to pass and the function *is* the interface);
* `ProblemError(Exception)` carrying the problem as a dataclass, `problem+json` raised, the 2xx
  body returned (a `204` is `None`);
* the runtime over `urllib.request` only: no `pip install`, no third-party dependency, typed with
  `from __future__ import annotations` so the file is its own contract;
* the gate: the committed `examples/users/py/client.py` byte for byte, `mypy --strict` over it,
  and `tests/client_e2e.py` — one happy path and one `problem+json` refusal, typed both ways,
  against the same running service. All three green.

What building it found (two rules the issue did not name): a frozen dataclass is not JSON
serializable by default, so the generated runtime carries a `_json_default` that turns a dataclass
into its fields and drops the `None` ones — the `omitempty` strictness the Go writer puts in the tag;
and mypy needs the query dict's pairs annotated (`cast('list[tuple[str, Any]]', ...)`), because the
optional values are `T | None` and inference alone cannot name the tuple. The document's own `Problem`
wins here too: when it names one, the generated file uses it and only `ProblemError` is the tool's.

## 9. The cancho client (#9), built as decided

The first consumer that is cancho itself: the same model, a fourth writer, but the output is
cancho — `struct` per component, a `fn` per operation over `packages/http-client` (cancho's own
client package; if it does not exist yet, over `conns` + `std.http` directly, as `psql.cho` talks
to PostgreSQL), `problem+json` a res struct the caller matches on. This is the slice that closes the
loop named in §2: a cancho service's document generating a cancho client, the whole contract in one
language, authority report on the generated client included. It waits on nothing external; it is
sequenced last because it is the one consumer whose *runtime* is cancho's to provide.

Built (2026-10-10): `examples/users/cho/client.cho`, from the same document, held by the same gate.
The module is the typed contract -- `res struct` per component, a strict `decode_*` (wrong kinds left
at their defaults), a `build_*` per operation, `problem+json` the document's own `Problem` -- and the
loop is the caller's, as §2 said and `web`'s is. What building it found: matching an owned schema
consumes it, so the writer's one walk per component emits every text at once (the struct, the drop
with its destructure, the decode with its locals and return) -- the discipline the other three
writers could defer because their languages' types are text, while cancho's are checked; and the
generated drops are recursive where lists appear, as `std.list`'s own `drop` is, because a loop's
residual is a whole list the checker cannot see is empty.

## 10. Open questions

1. **Second producer — answered (2026-10-10).** [`examples/petstore/openapi.json`](../examples/petstore/openapi.json)
   is a hand-written petstore exercising what the users API does not: `allOf`, `oneOf`, document and
   operation `security` (bearer), a header parameter, a `default` response, `servers`, enums. What it
   found, verified shape by shape: `allOf`/`oneOf` are **refused** (`SchemaUnknownKind` — the right
   discipline, the missing capability, #11); `security` is **silently ignored** — a secured operation
   generates with no token argument, a client that compiles and cannot work (#10, the correctness gap);
   header parameters are **silently dropped** by every writer (#12); `servers` are ignored (the caller
   sets the base — acceptable, undocumented); and `default` responses **work** (status 0, `$ref`
   resolved) — a capability this tool had and had not claimed. The reduced petstore (no `allOf`/`oneOf`)
   passes all four writers' strict checks, and found a cancho-writer bug the users document could not:
   `drop_*` over-declares `heap` for a component with no owned field (#13). The issues carry the work.
2. **cancho-web#16.** Until components below the schema root are written as `$ref`, inline shapes
   are written structurally by every writer. When it lands, the writers gain named types for them
   and this section shrinks.
3. **`security`.** #4's issue text mentions security schemes; the users document declares none, the
   model does not read them, and a document that did would be refused by nothing and typed by
   nothing. Named here so it is not discovered later: an operation with `security` should take a
   token argument, and that is a slice of its own.
4. **Headers as parameters.** `Where::InHeader` is modelled and dropped by the writers (`_` in TS,
   dropped in Go). The users document has none; the first document that has one decides their
   shape.
