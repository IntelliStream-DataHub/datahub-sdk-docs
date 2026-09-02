#!/usr/bin/env bash
# One-time setup: a venv with pytest and the DataHub Python SDK built from source.
#
# The SDK is a PyO3 extension, so there is no wheel to pip-install from the source
# tree — maturin compiles the Rust core into this venv. Re-run after changing the
# SDK if you want the docs tested against your local changes; that is the whole
# point of building from a path rather than from a release.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SDK="${DOCTEST_RUST_SDK_PATH:-$(cd "$HERE/../.." && pwd)/dataplatform-rust-sdk}"

[ -d "$SDK/datahub_python_bindings" ] || {
  echo "error: no SDK at $SDK" >&2
  echo "       set DOCTEST_RUST_SDK_PATH to your dataplatform-rust-sdk checkout." >&2
  exit 1
}

[ -d "$HERE/.venv" ] || python3 -m venv "$HERE/.venv"
"$HERE/.venv/bin/pip" install -q --upgrade pip maturin pytest pandas numpy

echo "building the SDK bindings into doctests/.venv (compiles Rust — slow the first time)…"
( cd "$SDK/datahub_python_bindings" \
  && VIRTUAL_ENV="$HERE/.venv" PATH="$HERE/.venv/bin:$PATH" maturin develop --release )

"$HERE/.venv/bin/python" -c 'import intellistream_datahub_sdk as s; print("SDK ready:", s.__name__)'

[ -f "$HERE/.env" ] || {
  cp "$HERE/.env.example" "$HERE/.env"
  echo "wrote doctests/.env from the example — point it at a stack before running."
}
echo "done. now: ./doctests/run.sh"
