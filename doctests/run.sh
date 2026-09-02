#!/usr/bin/env bash
# Run the documentation tutorial suite. Extra args go to pytest.
#
#   ./doctests/run.sh                          # every planned tutorial, Python
#   ./doctests/run.sh -k quickstart            # one page
#   ./doctests/run.sh --langs all              # Java and Rust too
#   ./doctests/run.sh --keep -s -k tutorial    # leave the data behind and watch it run
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -x "$HERE/.venv/bin/pytest" ] || { echo "run $HERE/setup.sh first" >&2; exit 1; }

# Run the whole suite unless the caller named specific tests. Without this, passing
# a file would run it *in addition to* everything else, which is a surprising way to
# spend four minutes when you asked for one file.
targets=()
for arg in "$@"; do
  [ -e "$arg" ] && targets+=("$arg")
done
[ ${#targets[@]} -eq 0 ] && targets=("$HERE")

exec "$HERE/.venv/bin/pytest" "${targets[@]}" "$@"
