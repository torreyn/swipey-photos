#!/bin/sh
# Build a single-file AppImage for ImageSwiper.
#
#   ./packaging/appimage/build-appimage.sh                    # needs appimagetool
#   ./packaging/appimage/build-appimage.sh --staging-only     # stop after staging
#   APPIMAGETOOL=/path/to/appimagetool ./packaging/appimage/build-appimage.sh
#
# What it does
#   1. Copies a *relocatable* CPython into ImageSwiper.AppDir/usr.
#   2. Installs ImageSwiper and its runtime dependencies into that interpreter's
#      site-packages (uv when available, pip otherwise).
#   3. Adds AppRun, the .desktop entry and the icon, then calls appimagetool.
#
# A relocatable interpreter is required because the bundle has to run on machines
# without Python installed. python-build-standalone builds qualify and are what
# `uv python install` downloads; a distribution python links against
# /usr/lib/.../libpython and cannot be copied. Point --python at one of them:
#
#   uv python install 3.13
#   ./packaging/appimage/build-appimage.sh --python "$(uv python find 3.13)"
#
# appimagetool is fetched separately from the upstream project
# (https://github.com/AppImage/appimagetool/releases). Set APPIMAGETOOL to a
# local copy, or run with --staging-only and package the AppDir later.
# This step is not part of CI: it needs the network and produces a ~150 MB file.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd -P)

PYTHON=
OUTPUT=$ROOT/build/appimage
STAGING_ONLY=0
APPIMAGETOOL=${APPIMAGETOOL:-}

usage() {
    cat <<'EOF'
Usage: build-appimage.sh [options]

Bundle ImageSwiper into an AppImage.

Options:
  --python PATH     relocatable interpreter to bundle (default: $APPIMAGE_PYTHON,
                    then the interpreter that `uv python find` reports)
  --output DIR      where to stage and write the artifact (default: build/appimage)
  --staging-only    build ImageSwiper.AppDir but skip appimagetool
  --appimagetool P  appimagetool binary (default: $APPIMAGETOOL, then PATH)
  -h, --help        show this help

Environment:
  APPIMAGE_PYTHON   same as --python
  APPIMAGETOOL      same as --appimagetool
  APPIMAGE_PIP_ARGS extra arguments for the dependency install, for example
                    "--no-index --find-links /path/to/wheels" on an offline box
EOF
}

fail() {
    printf 'build-appimage.sh: %s\n' "$1" >&2
    exit 1
}

usage_error() {
    printf 'build-appimage.sh: %s\n' "$1" >&2
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
        --output)
            [ $# -ge 2 ] || fail "--output needs a directory"
            OUTPUT=$2
            shift 2
            ;;
        --output=*) OUTPUT=${1#*=} ; shift ;;
        --staging-only) STAGING_ONLY=1 ; shift ;;
        --appimagetool)
            [ $# -ge 2 ] || fail "--appimagetool needs a path"
            APPIMAGETOOL=$2
            shift 2
            ;;
        --appimagetool=*) APPIMAGETOOL=${1#*=} ; shift ;;
        -h|--help) usage ; exit 0 ;;
        *) usage_error "unknown argument: $1" ;;
    esac
done

if [ -z "$PYTHON" ]; then
    PYTHON=${APPIMAGE_PYTHON:-}
fi
if [ -z "$PYTHON" ] && command -v uv >/dev/null 2>&1; then
    PYTHON=$(uv python find 3.13 2>/dev/null || true)
fi
[ -n "$PYTHON" ] || fail "no interpreter to bundle; pass --python (see the header for the uv commands)"
[ -x "$PYTHON" ] || fail "$PYTHON is not executable"

PYTHON=$(readlink -f "$PYTHON") || fail "cannot resolve $PYTHON"
PREFIX=$(dirname -- "$(dirname -- "$PYTHON")")
python_found=0
for candidate in "$PREFIX"/lib/python*/os.py; do
    if [ -f "$candidate" ]; then
        python_found=1
    fi
done
[ "$python_found" -eq 1 ] || fail "$PREFIX does not look like a CPython installation"

# A shared libpython would have to be found at runtime on the target machine.
if ldd "$PYTHON" 2>/dev/null | grep -q 'libpython'; then
    fail "$PYTHON links against a shared libpython, so it cannot be bundled.
  Use a relocatable build instead:
    uv python install 3.13
    ./packaging/appimage/build-appimage.sh --python \"\$(uv python find 3.13)\""
fi

VERSION=$("$PYTHON" -c 'import pathlib, re, sys
init = pathlib.Path(sys.argv[1]) / "src" / "image_swiper" / "__init__.py"
print(re.search(r"__version__ = \"([^\"]+)\"", init.read_text()).group(1))' "$ROOT")
[ -n "$VERSION" ] || fail "could not read the version from src/image_swiper/__init__.py"

APP_DIR=$OUTPUT/ImageSwiper.AppDir
SITE_REL=$("$PYTHON" -c 'import sys; print(f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages")')
PY_REL=$("$PYTHON" -c 'import sys; print(f"bin/python{sys.version_info.major}.{sys.version_info.minor}")')

printf 'Bundling Python from %s\n' "$PREFIX"
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/usr"
cp -a "$PREFIX/." "$APP_DIR/usr/"

# Trim what an image-sorting app never loads: headers, manual pages, the test
# suite, tkinter/tcl and ensurepip. Saves roughly a third of the bundle.
rm -rf "$APP_DIR/usr/include" "$APP_DIR/usr/share/man" "$APP_DIR/usr/share/doc" \
    "$APP_DIR/usr/lib/python"*"/test" "$APP_DIR/usr/share/tcl"* "$APP_DIR/usr/lib/tcl"* \
    "$APP_DIR/usr/lib/tk"* "$APP_DIR/usr/share/tk"* "$APP_DIR/usr/lib/python"*"/tkinter" \
    "$APP_DIR/usr/lib/python"*"/idlelib" "$APP_DIR/usr/lib/python"*"/ensurepip"
find "$APP_DIR/usr" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

BUNDLED_PY=$APP_DIR/usr/$PY_REL
SITE=$APP_DIR/usr/$SITE_REL
[ -x "$BUNDLED_PY" ] || fail "the staged interpreter is missing: $BUNDLED_PY"
mkdir -p "$SITE"

printf 'Installing ImageSwiper %s and its dependencies\n' "$VERSION"
# shellcheck disable=SC2086  # APPIMAGE_PIP_ARGS is a list on purpose
if command -v uv >/dev/null 2>&1; then
    uv pip install --python "$BUNDLED_PY" --target "$SITE" ${APPIMAGE_PIP_ARGS:-} "$ROOT"
else
    # shellcheck disable=SC2086
    "$BUNDLED_PY" -m pip install --no-cache-dir --target "$SITE" ${APPIMAGE_PIP_ARGS:-} "$ROOT"
fi

# PyQt6 ships far more than a QtWidgets application needs: QML, Quick3D, the
# Designer plugin, translations and the Qt Quick tooling. Dropping them keeps the
# AppImage at roughly two thirds of the wheel's footprint. The Qt libraries the
# widgets stack actually loads (Core, Gui, Widgets, DBus, XcbQpa, Svg, Network,
# OpenGL) stay.
QT_LIB=$SITE/PyQt6/Qt6
rm -rf "$QT_LIB/qml" "$QT_LIB/qsci" "$QT_LIB/translations" \
    "$QT_LIB/plugins/assetimporters" "$QT_LIB/plugins/sceneparsers"
for lib in Quick Qml Quick3D Designer ShaderTools LabsStyleKit; do
    rm -f "$QT_LIB"/lib/libQt6"$lib"* 2>/dev/null || true
done

cat > "$APP_DIR/AppRun" <<'APPRUN'
#!/bin/sh
# Entry point of the ImageSwiper AppImage: run the bundled interpreter, which
# finds its standard library relative to its own path inside the bundle.
set -eu
# Resolve our own directory instead of trusting $APPDIR: the runtime does set it,
# but the variable can also be inherited from an unrelated AppImage (VS Code, for
# instance) when someone runs AppRun by hand.
APPDIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
exec "$APPDIR/usr/bin/python3" -m image_swiper "$@"
APPRUN
chmod +x "$APP_DIR/AppRun"

# The desktop entry names the launcher, the icon and the WM_CLASS; the AppImage
# runtime supplies the real path when it integrates the bundle into a menu.
sed 's/^Exec=.*/Exec=image-swiper/' "$SCRIPT_DIR/../image-swiper.desktop" \
    > "$APP_DIR/image-swiper.desktop"
cp "$SCRIPT_DIR/../icons/hicolor/256x256/apps/image-swiper.png" "$APP_DIR/.DirIcon"
cp "$SCRIPT_DIR/../icons/hicolor/scalable/apps/image-swiper.svg" "$APP_DIR/image-swiper.svg"

printf 'Staged %s\n' "$APP_DIR"
"$BUNDLED_PY" -c 'import image_swiper, PyQt6.QtWidgets, PIL; print("bundle check:", image_swiper.__file__)' \
    || fail "the staged bundle cannot import its dependencies"

if [ "$STAGING_ONLY" -eq 1 ]; then
    printf 'Skipping appimagetool (--staging-only)\n'
    exit 0
fi

if [ -z "$APPIMAGETOOL" ]; then
    APPIMAGETOOL=$(command -v appimagetool || true)
fi
if [ -z "$APPIMAGETOOL" ]; then
    printf 'appimagetool was not found.\n' >&2
    printf 'Download it from https://github.com/AppImage/appimagetool/releases, then rerun with\n' >&2
    printf '  APPIMAGETOOL=/path/to/appimagetool %s\n' "$0" >&2
    printf 'The AppDir is ready at %s\n' "$APP_DIR" >&2
    exit 2
fi

ARCH=$(uname -m)
TARGET=$OUTPUT/image-swiper-$VERSION-$ARCH.AppImage
printf 'Packaging %s\n' "$TARGET"
ARCH=$ARCH "$APPIMAGETOOL" "$APP_DIR" "$TARGET"
printf 'Wrote %s\n' "$TARGET"
