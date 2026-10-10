#!/bin/bash
# The gate (#6): the committed client is what the pinned document says.
#
#   scripts/check-client.sh
#
# Regenerates the TypeScript client from the checked-in document and diffs
# it against the committed one -- a contract change without a regenerated
# client is a red build, not an integration break. pgen's discipline, the
# acceptance test of the whole tool: server and client cannot disagree
# silently.
#
#   CANCHO       the cancho compiler binary     (default: cancho on PATH)
#   BIN          the built clientgen            (default: build/clientgen)
#   USERS_REV    cancho-web revision the document is fetched from, when
#                FETCH_DOC=1 (CI pins WEB_REV instead and checks out the repo)
set -euo pipefail
here=$(cd "$(dirname "$0")/.." && pwd)
CANCHO=${CANCHO:-cancho}
BIN=${BIN:-$here/build/clientgen}
DOC=${DOC:-$here/examples/users/openapi.json}

if [ ! -x "$BIN" ]; then
  echo "check-client: building clientgen first" >&2
  "$here/scripts/build.sh" "$BIN"
fi

# Fetch the document from cancho-web at the revision CI pins, when asked: the
# local copy is the same bytes, but the gate's point is the *pinned* document.
if [ "${FETCH_DOC:-0}" = "1" ]; then
  WEB_DIR=${WEB_DIR:-$here/../cancho-web}
  REV=${USERS_REV:-$(sed -n 's/^ *WEB_REV: *//p' "$here/.github/workflows/ci.yml")}
  (cd "$WEB_DIR" && git checkout -q "$REV")
  cp "$WEB_DIR/examples/users/openapi.json" "$DOC"
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
"$BIN" "$DOC" --typescript -o "$tmp/client.ts"
"$BIN" "$DOC" --go -o "$tmp/client.go"
"$BIN" "$DOC" --python -o "$tmp/client.py"
"$BIN" "$DOC" --cancho -o "$tmp/client.cho"
# The generated cancho is canonicalised by `cancho fmt` before the diff: the
# generator writes it the way `pgen` does, and the committed file is what fmt
# makes of it (the issue's own words: "formatted by `cancho fmt`").
if [ -n "${CANCHO:-}" ] && [ -x "${CANCHO:-}" ]; then
  "$CANCHO" fmt "$tmp/client.cho" >/dev/null
fi

fail=0
if ! diff -u "$here/examples/users/ts/client.ts" "$tmp/client.ts"; then
  echo "check-client: examples/users/ts/client.ts is stale: regenerate it with" >&2
  echo "  $BIN $DOC --typescript -o examples/users/ts/client.ts" >&2
  fail=1
fi
if ! diff -u "$here/examples/users/go/client.go" "$tmp/client.go"; then
  echo "check-client: examples/users/go/client.go is stale: regenerate it with" >&2
  echo "  $BIN $DOC --go -o examples/users/go/client.go" >&2
  fail=1
fi
if ! diff -u "$here/examples/users/py/client.py" "$tmp/client.py"; then
  echo "check-client: examples/users/py/client.py is stale: regenerate it with" >&2
  echo "  $BIN $DOC --python -o examples/users/py/client.py" >&2
  fail=1
fi
if ! diff -u "$here/examples/users/cho/client.cho" "$tmp/client.cho"; then
  echo "check-client: examples/users/cho/client.cho is stale: regenerate it with" >&2
  echo "  $BIN $DOC --cancho -o examples/users/cho/client.cho" >&2
  fail=1
fi
if [ "$fail" != 0 ]; then exit 1; fi
echo "check-client: all four clients match the document"
