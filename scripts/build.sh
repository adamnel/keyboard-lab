#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cache="$root/.cache"
upstream="$cache/vial-qmk"
venv="$root/.venv"
lock="$root/firmware/upstream.lock.json"
output="$root/build"
make_command=${MAKE:-make}

if [ ! -x "$venv/bin/python" ] || [ ! -d "$upstream/.git" ]; then
    echo 'Run scripts/bootstrap.sh to prepare the project-local build environment.' >&2
    exit 1
fi
for program in "$make_command" arm-none-eabi-gcc arm-none-eabi-objcopy; do
    if ! command -v "$program" >/dev/null; then
        echo "Missing build tool: $program" >&2
        exit 1
    fi
done

# Build and publish through one checkout at a time.
if ! mkdir "$cache/build.lock"; then
    echo "Build lock already present at $cache/build.lock." >&2
    exit 1
fi
trap 'rmdir "$cache/build.lock"' 0
trap 'exit 1' HUP INT TERM

build_target=$("$venv/bin/python" - "$lock" "$upstream" <<'PY'
import json
import subprocess
import sys

with open(sys.argv[1]) as file:
    lock = json.load(file)
upstream = sys.argv[2]

def git(*args):
    return subprocess.check_output(["git", "-C", upstream, *args], text=True).strip()

if git("rev-parse", "HEAD") != lock["commit"] or git("status", "--porcelain", "--untracked-files=no"):
    sys.exit("The cached upstream checkout differs from the locked source.")

# Preserve each git status prefix, including the leading space on the first line.
status = subprocess.check_output(["git", "-C", upstream, "submodule", "status", "--recursive"], text=True)
submodules = {line[1:].split()[1]: line for line in status.splitlines()}
for directory, entry in lock["submodules"].items():
    if not entry["build"]:
        continue
    line = submodules.get(directory, "")
    if not line.startswith(" " + entry["commit"] + " "):
        sys.exit(f"Cached submodule {directory} differs from the lock. Run scripts/bootstrap.sh.")
print(lock["target"] + ":" + lock["keymap"])
PY
)
target=${build_target%:*}
keymap=${build_target#*:}
staged_keymap="$upstream/keyboards/$target/keymaps/$keymap"
mkdir -p "$(dirname "$staged_keymap")"
rm -rf "$staged_keymap"
cp -R "$root/firmware/keymaps/$keymap" "$staged_keymap"

# Keep QMK configuration local and omit machine- and date-dependent version text.
export PATH="$venv/bin:$PATH"
mkdir -p "$cache/qmk-userspace"
cd "$upstream"
firmware=$(printf '%s_%s.uf2' "$target" "$keymap" | tr / _)
rm -f "$firmware"
"$make_command" "$build_target" SKIP_VERSION=yes QMK_USERSPACE="$cache/qmk-userspace"
test -s "$firmware"
mkdir -p "$output"
cp "$firmware" "$output/$firmware.tmp"
mv "$output/$firmware.tmp" "$output/$firmware"
printf '%s\n' "$output/$firmware"
