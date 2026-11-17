#!/bin/sh
# Build the single-file Swipey Photos executable with PyInstaller.
#
#   ./scripts/build.sh                      # -> dist/swipey-photos
#   ./scripts/build.sh --clean              # drop build/venv, rebuild from scratch
#   PYTHON=python3.12 ./scripts/build.sh    # pick the interpreter for the venv
#
# What it does
#   1. Creates build/venv (or reuses it) and installs the project plus the
#      `binary` extra from pyproject.toml — no global site-packages are touched.
#   2. Runs PyInstaller with swipey-photos.spec (one file, windowed, named
#      `swipey-photos`).
#   3. Smoke-tests the result: `dist/swipey-photos --version` must print the
#      version that pyproject.toml declares.
#
# The artifact bundles CPython, PyQt6 and Pillow, so it runs on a machine
# without Python. It is *not* fully static: the Qt platform plugins still link
# against the system libraries listed in the README (libxcb-cursor0, libegl1,
# libxkbcommon-x11-0, …). For a bundle that also carries those, use
# packaging/appimage/build-appimage.sh.
#
# CI runs the same recipe in .github/workflows/release.yml and attaches the
# binary to the GitHub Release.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd -P)

PYTHON=${PYTHON:-python3}
VENV=$ROOT/build/venv
OUTPUT=$ROOT/dist
CLEAN=0

usage() {
    cat <<'EOF'
Usage: build.sh [options]

Build dist/swipey-photos with PyInstaller.

Options:
  --python PATH   interpreter used to create the build venv (default: $PYTHON,
                  then python3)
  --venv DIR      build venv to create or reuse (default: build/venv)
  --output DIR    directory for the executable (default: dist)
  --clean         remove the build venv and PyInstaller work directory first
  -h, --help      show this help

Environment:
  PYTHON          same as --python
  PIP_ARGS        extra arguments for the dependency install, for example
                  "--no-index --find-links /path/to/wheels" on an offline box
EOF
}

fail() {
    printf 'build.sh: %s\n' "$1" >&2
    exit 1
}

usage_error() {
    printf 'build.sh: %s\n' "$1" >&2
    usage >&2
    exit 2
}

while [ $# -gt 0 ]; do
    case $1 in
        --python)
            [ $# -ge 2 ] || fail "--python needs an interpreter"
            PYTHON=$2
            shift 2
            ;;
        --python=*) PYTHON=${1#*=} ; shift ;;
        --venv)
            [ $# -ge 2 ] || fail "--venv needs a directory"
            VENV=$2
            shift 2
            ;;
        --venv=*) VENV=${1#*=} ; shift ;;
        --output)
            [ $# -ge 2 ] || fail "--output needs a directory"
            OUTPUT=$2
            shift 2
            ;;
        --output=*) OUTPUT=${1#*=} ; shift ;;
        --clean) CLEAN=1 ; shift ;;
        -h|--help) usage ; exit 0 ;;
        *) usage_error "unknown argument: $1" ;;
    esac
done

command -v "$PYTHON" >/dev/null 2>&1 || fail "interpreter not found: $PYTHON"

if [ "$CLEAN" -eq 1 ]; then
    rm -rf "$VENV" "$ROOT/build/pyinstaller"
fi

if [ ! -x "$VENV/bin/python" ]; then
    printf 'build.sh: creating venv in %s\n' "$VENV"
    "$PYTHON" -m venv "$VENV" || fail "could not create a venv; install python3-venv"
fi

printf 'build.sh: installing the project and PyInstaller\n'
# shellcheck disable=SC2086  # PIP_ARGS is intentionally word-split
"$VENV/bin/python" -m pip install --disable-pip-version-check --quiet \
    "${ROOT}[binary]" ${PIP_ARGS:-} || fail "dependency install failed"

mkdir -p "$OUTPUT"
printf 'build.sh: running PyInstaller\n'
# --distpath/--workpath/--clean/--noconfirm are honoured with a spec file; the
# build options themselves live in swipey-photos.spec.
"$VENV/bin/python" -m PyInstaller \
    --clean \
    --noconfirm \
    --workpath "$ROOT/build/pyinstaller" \
    --distpath "$OUTPUT" \
    "$ROOT/swipey-photos.spec" || fail "PyInstaller failed"

BINARY=$OUTPUT/swipey-photos
[ -x "$BINARY" ] || fail "PyInstaller did not produce $BINARY"

printf 'build.sh: smoke-testing %s\n' "$BINARY"
BUILT=$("$BINARY" --version) || fail "$BINARY --version failed"
EXPECTED="Swipey Photos $("$VENV/bin/python" -c 'import swipey_photos; print(swipey_photos.__version__)')"
[ "$BUILT" = "$EXPECTED" ] || fail "version mismatch: expected '$EXPECTED', got '$BUILT'"

printf 'build.sh: %s (%s)\n' "$BINARY" "$BUILT"
printf 'build.sh: size %s\n' "$(du -h "$BINARY" | cut -f1)"
printf 'build.sh: try it with %s --dry-run ~/Pictures/unsorted\n' "$BINARY"
