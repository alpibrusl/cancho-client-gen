#!/bin/bash
# Build the clientgen tool against the pinned compiler.
#
#   scripts/build.sh build/clientgen
#
# The compiler is fetched from the cancho repository at the revision CI builds
# with (read from .github/workflows/ci.yml, so this text cannot drift from it).
# A package store records no hash of the `std` it was published against, so
# the compiler revision is part of the contract.
#
#   CANCHO       the cancho compiler binary     (default: cancho on PATH)
#   CANCHO_DIR   a checkout of cancho           (default: ../cancho)
set -euo pipefail
here=$(cd "$(dirname "$0")/.." && pwd)
CANCHO=${CANCHO:-cancho}
CANCHO_DIR=${CANCHO_DIR:-$here/../cancho}
out=$1

mkdir -p "$(dirname "$out")"
if [ "$CANCHO" = "cancho" ] && [ ! -x "$CANCHO" ]; then
  REV=$(sed -n 's/^ *CANCHO_REV: *//p' "$here/.github/workflows/ci.yml")
  (cd "$CANCHO_DIR" && git checkout "$REV" && cargo build --release -p cancho)
  CANCHO="$CANCHO_DIR/target/release/cancho"
fi
"$CANCHO" build --std --backend cranelift "$here/src/clientgen.cho" -o "$out"
