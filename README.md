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

**Slices 1 and 2 built: the reader and the model.** [`src/clientgen.cho`](src/clientgen.cho) reads the document
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

The byte-verified `examples/users/openapi.json` reads as `ok 5 operations, 4 components`. The work is sequenced
in [the epic (#2)](https://github.com/alpibrusl/cancho-client-gen/issues/2); the writers (#5, #7, #8), the
committed-output half of the gate (#6) and the cancho client (#9) are not started. Sequenced after
[cancho-web#16](https://github.com/alpibrusl/cancho-web/issues/16): components used below the schema root must
be written as `$ref`, not inline -- named shapes mean a class per component instead of an anonymous one, and
a client generator is the consumer that wants them.

## What you get

* **The contract as a file, on both sides.** The server pins its document byte for byte; the client is
  regenerated from the same file, and CI regenerates and diffs, so a change to the API is a change to a
  generated client that review sees.
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

The reader and the model are built; the writers are slices 4–6 ([#5](https://github.com/alpibrusl/cancho-client-gen/issues/5),
[#7](https://github.com/alpibrusl/cancho-client-gen/issues/7), [#8](https://github.com/alpibrusl/cancho-client-gen/issues/8)).
What runs today is the gate's first half -- the answer to "is this the document a client can come from" --
and the model, printed:

```
scripts/build.sh build/clientgen
build/clientgen examples/users/openapi.json --check
ok 5 operations, 4 components
build/clientgen examples/users/openapi.json --model
get /users -> listUsers (2 parameters, body none, 2 responses: 200=Page 422=Problem )
...
```

The planned shape, once the TypeScript target lands (the gate's committed-output half is
[issue #6](https://github.com/alpibrusl/cancho-client-gen/issues/6)):

```
clientgen examples/users/openapi.json --typescript -o clients/ts
git diff --exit-code clients/ts
```

## Repository layout

```
src/clientgen.cho         the reader and the tool: `std.json`'s tape, the shape checks; --check, --model
src/model.cho             the model: Method, Where, Schema (with $ref resolved to a name), Operation, ...; res all the way down
examples/users/openapi.json  cancho-web's byte-verified document, the first test input
tests/e2e.py              the end-to-end tests: the document read and modelled, every refusal exercised
scripts/build.sh          build against the pinned compiler
docs/authority.json       what the tool can touch, as last approved; CI fails when it changes
docs/index.html           the project page
LICENSE                   EUPL-1.2
```

## License

[EUPL-1.2](LICENSE).
