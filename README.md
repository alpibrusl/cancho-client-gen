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

**Design. The epic is open, the first slice is not started.** There is no `src/` yet; the work is sequenced in
[the epic (#2)](https://github.com/alpibrusl/cancho-client-gen/issues/2) and its seven task issues (#3–#9).
Sequenced after [cancho-web#16](https://github.com/alpibrusl/cancho-web/issues/16): components used below the
schema root must be written as `$ref`, not inline -- named shapes mean a class per component instead of an
anonymous one, and a client generator is the consumer that wants them.

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

- Nothing yet: this repository is at the design stage (the first slice, a JSON reader over cancho's own
  buffers, is [issue #3](https://github.com/alpibrusl/cancho-client-gen/issues/3)). When there is a `src/`,
  the requirements will be the **cancho** compiler at the revision this repository's CI builds with, plus Rust
  to build it.

## Quick start

The planned shape (not built yet; the gate that makes it a gate is
[issue #6](https://github.com/alpibrusl/cancho-client-gen/issues/6)):

```
clientgen examples/users/openapi.json --typescript -o clients/ts
git diff --exit-code clients/ts
```

## Repository layout

```
README.md                 this file
docs/index.html           the project page
LICENSE                   EUPL-1.2
```

## License

[EUPL-1.2](LICENSE).
