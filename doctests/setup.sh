#!/usr/bin/env bash
# One-time setup: a venv with pytest and the DataHub Python SDK built from source.
#
# The SDK is a PyO3 extension, so there is no wheel to pip-install from the source
# tree — maturin compiles the Rust core into this venv. Re-run after changing the
# SDK if you want the docs tested against your local changes; that is the whole
# point of building from a path rather than from a release.
#
#   DOCTEST_RUST_SDK_PATH  the SDK checkout to build (default ../../dataplatform-rust-sdk)
#   DOCTEST_VENV           the venv to use (default doctests/.venv); run.sh reads it too
#   DOCTEST_SDK_PREBUILT=1 the venv already has the bindings built from that checkout, so
#                          skip the Rust build. For CI, where the SDK's own test step has
#                          just built them and a second release build would be minutes
#                          of rustc next to a running stack.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${DOCTEST_VENV:-$HERE/.venv}"
SDK="${DOCTEST_RUST_SDK_PATH:-$(cd "$HERE/../.." && pwd)/dataplatform-rust-sdk}"

[ -d "$SDK/datahub_python_bindings" ] || {
  echo "error: no SDK at $SDK" >&2
  echo "       set DOCTEST_RUST_SDK_PATH to your dataplatform-rust-sdk checkout." >&2
  exit 1
}

[ -d "$VENV" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r "$HERE/requirements.txt"

if [ -n "${DOCTEST_SDK_PREBUILT:-}" ]; then
  echo "DOCTEST_SDK_PREBUILT is set: using the SDK bindings already built into $VENV"
else
  echo "building the SDK bindings into $VENV (compiles Rust — slow the first time)…"
  ( cd "$SDK/datahub_python_bindings" \
    && VIRTUAL_ENV="$VENV" PATH="$VENV/bin:$PATH" maturin develop --release )
fi

"$VENV/bin/python" -c 'import intellistream_datahub_sdk as s; print("SDK ready:", s.__name__)'

[ -f "$HERE/.env" ] || {
  cp "$HERE/.env.example" "$HERE/.env"
  echo "wrote doctests/.env from the example — point it at a stack before running."
}
echo "done. now: ./doctests/run.sh"
