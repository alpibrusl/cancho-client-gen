# cancho-client-gen

[![ci](https://github.com/alpibrusl/cancho-client-gen/actions/workflows/ci.yml/badge.svg)](https://github.com/alpibrusl/cancho-client-gen/actions/workflows/ci.yml)

**The contract, both ways.** cancho-client-gen consumes the byte-verified OpenAPI 3.1 document that
[`cancho-web`](https://github.com/alpibrusl/cancho-web) generates (pinned byte for byte by that repository's
end-to-end test) and writes strictly typed client libraries, in the pgen tradition
([`cancho-pg`](https://github.com/alpibrusl/cancho-pg) turns `queries.sql` into typed cancho functions by asking
the database; this turns `openapi.json` into typed clients by reading the document). A tool for
[cancho](https://github.com/alpibrusl/cancho), a typed systems language with linear ownership and capability
effects: the clients it writes make no foreign call, and `cancho authority` on the generator says so.

## Why the document, not the declaration

The declaration is a running program and a second source of truth: a generator that read it would have to run
the service or re-read `.cho` source ([cancho-web's design.md](https://github.com/alpibrusl/cancho-web/blob/main/docs/design.md) §9.9
says why the same argument rejected generated records there). The document is a file, already verified --
cancho-web's test holds what the service serves byte for byte against the checked-in `openapi.json`, and
Schemathesis generates requests from it -- and consuming it keeps the tool useful for any OpenAPI 3.1
producer, not just cancho-web. One contract, both directions: the server is held to the document by tests, the
client is written from the document by this tool, and neither side hand-writes the other's half.

## Status

**All seven slices built: the reader, the model, three targets, the gate, the cancho client.** [`src/clientgen.cho`](src/clientgen.cho) reads the document
with `std.json`'s tape -- no copy, no foreign code -- and refuses what is not an OpenAPI 3.1 document (nine
shape refusals, nothing written for an invalid one, pgen's discipline). [`src/model.cho`](src/model.cho)
models what it reads, in the enum-and-struct discipline of [cancho-web#27](https://github.com/alpibrusl/cancho-web/issues/27):
a `Method` and a `Where` enum, a `Schema` enum with `Ref` holding the component's *name*, a res struct per
thing (`Operation`, `Parameter`, `Response`, `Component`, `Doc`), all `res` so the checker holds the tool to
freeing the model. `$ref`s resolve to names -- a reference that points nowhere is a named error, not a
best-effort inline -- and a response that is a `$ref` to a named response component (`422` in the users
document) resolves to its `problem+json` schema. `clientgen <doc> --model` prints it:

```
get /users -> listUsers (2 parameters, body none, 2 responses: 200=Page 422=Problem )
post /users -> createUser (0 parameters, body NewUser, 5 responses: 201=User 400=Problem 415=Problem 422=Problem 503=Problem )
component NewUser: object
```

The byte-verified `examples/users/openapi.json` reads as `ok 5 operations, 4 components`. The TypeScript target
([#5](https://github.com/alpibrusl/cancho-client-gen/issues/5)) is built:
[`examples/users/ts/client.ts`](examples/users/ts/client.ts) is generated from that document -- an interface per
component, a typed function per operation (`getUser(id: number): Promise<User>`), `problem+json` as
`ProblemError` -- and compiles under `tsc --strict`. The gate ([#6](https://github.com/alpibrusl/cancho-client-gen/issues/6))
is built: [`scripts/check-client.sh`](scripts/check-client.sh) regenerates the client from the document and diffs
(`git diff --exit-code` -- a contract change without a regenerated client is a red build, not an integration
break), and [`tests/client_e2e.mjs`](tests/client_e2e.mjs) runs the committed client against the running
cancho-web users service -- one happy path and one `problem+json` refusal, typed both ways. The Go target ([#7](https://github.com/alpibrusl/cancho-client-gen/issues/7)) is built:
[`examples/users/go/client.go`](examples/users/go/client.go) -- a `type` per component, a function per
operation over `net/http` (`getUser(c *Client, id int) (User, error)`), `problem+json` as `*ProblemError`
implementing `error` -- compiles under `go build` and `go vet`, held by the same gate. The Python target
([#8](https://github.com/alpibrusl/cancho-client-gen/issues/8)) is built:
[`examples/users/py/client.py`](examples/users/py/client.py) -- a frozen `@dataclass` per component, a
typed method per operation over `urllib.request` (no third-party package), `problem+json` as
`ProblemError` -- passes `mypy --strict` and runs against the live service in
[`tests/client_e2e.py`](tests/client_e2e.py). The design is [`docs/design.md`](docs/design.md). The cancho client
([#9](https://github.com/alpibrusl/cancho-client-gen/issues/9)) is built:
[`examples/users/cho/client.cho`](examples/users/cho/client.cho) -- a `res struct` per component with a
strict `decode_*` (a field of the wrong kind is left at its default, never guessed), a `build_*` fn per
operation (method, interpolated target, query), `problem+json` the document's own `Problem` matched on --
type-checks under `cancho check`, is `cancho fmt`-canonical, and is held by the same gate. The poller
loop is the caller's (as `web`'s is): the generated module is the typed contract, and the program that
uses it owns its loop and its authority row. The work is sequenced in
[the epic (#2)](https://github.com/alpibrusl/cancho-client-gen/issues/2); the epic is complete. Sequenced after
[cancho-web#16](https://github.com/alpibrusl/cancho-web/issues/16): components used below the schema root must
be written as `$ref`, not inline -- named shapes mean a class per component instead of an anonymous one, and
a client generator is the consumer that wants them.

## What you get

* **The contract as a file, on both sides.** The server pins its document byte for byte; the client is
  regenerated from the same file, and the gate (`scripts/check-client.sh`) regenerates and diffs in CI, so a
  change to the API is a red build without a regenerated client, never an integration break.
* **Strict types, no coercion.** A response body that breaks the schema is refused, not coerced; every error
  the document declares as `problem+json` (RFC 9457) is a typed error the client can switch on.
* **A class per component.** A named shape in the document (`User`, `Page`, `Problem`) is a named class in the
  client, not an anonymous one ([cancho-web#16](https://github.com/alpibrusl/cancho-web/issues/16) makes the
  document name them).
* **No foreign call.** The generated clients are cancho over `http.client`, and `cancho authority` on the
  generator itself reports what it can touch.
* **pgen's discipline.** Nothing is written for an invalid document: a file that does not validate as
  OpenAPI 3.1 produces no output and an error, the way `pgen` asks the database instead of trusting the
  `.sql` file.

## Requirements

- The **cancho** compiler at the revision this repository's CI builds with (`CANCHO_REV` in
  [`.github/workflows/ci.yml`](.github/workflows/ci.yml)). A package store records no hash of the `std` it was
  published with, so the compiler revision is part of the contract.
- Rust, to build that compiler (its `rust-toolchain.toml` pins the toolchain).
- `python3`, to run the end-to-end tests.

## Quick start

All seven slices are built. What runs today:

```
scripts/build.sh build/clientgen
build/clientgen examples/users/openapi.json --check
ok 5 operations, 4 components
build/clientgen examples/users/openapi.json --typescript -o examples/users/ts/client.ts
```

The generated client ([`examples/users/ts/client.ts`](examples/users/ts/client.ts), committed):

```typescript
export async function getUser(id: number): Promise<User> {
  return request("get", `/users/${id}`, undefined, undefined);
}
export async function listUsers(options?: { limit?: number, offset?: number }): Promise<Page> {
  return request("get", `/users`, options, undefined);
}
```

The gate ([#6](https://github.com/alpibrusl/cancho-client-gen/issues/6)):

```
scripts/check-client.sh     # regenerate from the document, git diff --exit-code
node tests/client_e2e.mjs   # the committed client, against the running users service
```

The second command builds the users service with cancho-web's own `scripts/build.sh` (its pinned compiler and
locked packages), starts it, and calls through the compiled client:

```
ok  createUser returns a typed User (id: number)
ok  listUsers returns a typed Page
ok  a refused body throws ProblemError
ok  every error at once (2 for this body)
ok  each error carries pointer/code/detail
```

Server and client cannot disagree silently: the document pins the server (cancho-web's e2e holds what it serves
byte for byte), the same document pins the client (the gate), and the live check holds them to each other.

## Repository layout

```
src/clientgen.cho         the reader and the tool: `std.json`'s tape, the shape checks; --check, --model, --typescript
src/model.cho             the model: Method, Where, Schema (with $ref resolved to a name), Operation, ...; res all the way down
src/ts.cho                the TypeScript writer: an interface per component, a function per operation, ProblemError
src/gow.cho               the Go writer: a type per component, a function per operation, ProblemError implementing error
src/py.cho                the Python writer: a frozen dataclass per component, a typed method per operation, ProblemError
src/cancho.cho            the cancho writer: a res struct per component, a build fn per operation, the caller owns the loop
examples/users/openapi.json  cancho-web's byte-verified document, the first test input
examples/users/ts/client.ts  the generated TypeScript client, committed; the gate holds it against the document
examples/users/go/client.go  the generated Go client, committed; go build and go vet in CI
examples/users/py/client.py  the generated Python client, committed; mypy --strict and a live run in CI
docs/design.md           the design the slices were built against
examples/users/cho/client.cho  the generated cancho client, committed; cancho check and fmt in CI
tests/e2e.py              the end-to-end tests: the document read and modelled, every refusal, tsc --strict
tests/client_e2e.mjs      the committed TypeScript client against the running users service
tests/client_e2e.py       the committed Python client against the running users service
scripts/check-client.sh   the gate: regenerate, git diff --exit-code
scripts/build.sh          build against the pinned compiler
docs/authority.json       what the tool can touch, as last approved; CI fails when it changes
docs/index.html           the project page
LICENSE                   EUPL-1.2
```

## License

[EUPL-1.2](LICENSE).
