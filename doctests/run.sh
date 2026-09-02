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
exec "$HERE/.venv/bin/pytest" "$HERE" "$@"
