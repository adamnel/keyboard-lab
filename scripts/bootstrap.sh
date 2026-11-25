#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python=${PYTHON:-python3.15}
cache="$root/.cache"
upstream="$cache/vial-qmk"
lock="$root/firmware/upstream.lock.json"

"$python" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 15) else "Use Python 3.15.x (set PYTHON if needed).")'
mkdir -p "$cache"
if [ ! -x "$root/.venv/bin/python" ]; then
    "$python" -m venv "$root/.venv"
fi
venv_python="$root/.venv/bin/python"
"$venv_python" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 15) else "Replace the project cache venv with Python 3.15.x.")'
"$venv_python" -m pip install --no-deps -r "$root/scripts/build-requirements.lock"
"$venv_python" -m pip install --no-deps -r "$root/scripts/runtime-requirements.lock"
"$venv_python" -m pip check

url=$("$venv_python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["repository"])' "$lock")
commit=$("$venv_python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["commit"])' "$lock")
if [ ! -d "$upstream/.git" ]; then
    git init "$upstream"
    git -C "$upstream" remote add origin "$url"
fi
if [ "$(git -C "$upstream" remote get-url origin)" != "$url" ]; then
    echo "Unexpected upstream remote in $upstream." >&2
    exit 1
fi
if ! git -C "$upstream" cat-file -e "$commit^{commit}" 2>/dev/null; then
    git -C "$upstream" fetch --depth=1 origin "$commit"
fi
git -C "$upstream" -c advice.detachedHead=false checkout --detach "$commit"

# Dependencies use the gitlinks in the pinned checkout.
"$venv_python" - "$lock" "$upstream" <<'PY'
import json
import subprocess
import sys

with open(sys.argv[1]) as file:
    lock = json.load(file)
upstream = sys.argv[2]
paths = [path for path, entry in lock["submodules"].items() if entry["build"]]
subprocess.run(["git", "-C", upstream, "submodule", "update", "--init", "--checkout", "--", *paths], check=True)
PY
