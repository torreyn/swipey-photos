#!/bin/sh
# Install the ImageSwiper desktop entry and icon set for the current user.
#
#   ./packaging/install-desktop.sh                    # ~/.local (or $XDG_DATA_HOME)
#   sudo ./packaging/install-desktop.sh --prefix /usr # system-wide
#   ./packaging/install-desktop.sh --uninstall        # remove it again
#
# Everything is copied from this directory, so the script works from a source
# checkout or from the unpacked sdist. It never touches the Python environment:
# the desktop entry launches the `image-swiper` console script, so install the
# package first (`pip install .` in the checkout).
#
# Packagers staging a package build pass --destdir; cache updates are skipped in
# that case because the files are not visible at their final paths yet.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
DATA_FILE="$SCRIPT_DIR/image-swiper.desktop"
ICONS_SRC="$SCRIPT_DIR/icons"

PREFIX=$HOME/.local
PREFIX_SET=0
DATA_ROOT=
DESTDIR=
UNINSTALL=0

usage() {
    cat <<'EOF'
Usage: install-desktop.sh [options]

Install (or remove) the ImageSwiper desktop entry and icons.

Options:
  --prefix DIR     install below DIR/share (default: ~/.local, or
                   $XDG_DATA_HOME when that variable is set)
  --destdir DIR    prepend DIR to every installed path, for packaging; cache
                   updates are skipped
  --uninstall      remove the desktop entry and icons instead of installing them
  -h, --help       show this help

Files:
  <data>/applications/image-swiper.desktop
  <data>/icons/hicolor/<size>/apps/image-swiper.{png,svg}
EOF
}

fail() {
    printf 'install-desktop.sh: %s\n' "$1" >&2
    exit 1
}

usage_error() {
    printf 'install-desktop.sh: %s\n' "$1" >&2
    usage >&2
    exit 2
}

while [ $# -gt 0 ]; do
    case $1 in
        --prefix)
            [ $# -ge 2 ] || fail "--prefix needs a directory"
            PREFIX=$2
            PREFIX_SET=1
            shift 2
            ;;
        --prefix=*) PREFIX=${1#*=} PREFIX_SET=1 ; shift ;;
        --destdir)
            [ $# -ge 2 ] || fail "--destdir needs a directory"
            DESTDIR=$2
            shift 2
            ;;
        --destdir=*) DESTDIR=${1#*=} ; shift ;;
        --uninstall|-u) UNINSTALL=1 ; shift ;;
        -h|--help) usage ; exit 0 ;;
        *) usage_error "unknown argument: $1" ;;
    esac
done

[ -n "$PREFIX" ] || fail "--prefix must not be empty"
# An explicit --prefix wins; otherwise honour XDG_DATA_HOME when it is set.
if [ -z "$DATA_ROOT" ]; then
    if [ "$PREFIX_SET" -eq 0 ] && [ -n "${XDG_DATA_HOME:-}" ]; then
        DATA_ROOT=$XDG_DATA_HOME
    else
        DATA_ROOT="$PREFIX/share"
    fi
fi
DATA_ROOT="$DESTDIR$DATA_ROOT"

APPLICATIONS_DIR="$DATA_ROOT/applications"
ICONS_DIR="$DATA_ROOT/icons"

[ -f "$DATA_FILE" ] || fail "missing $DATA_FILE (run this script from the packaging directory of a release tarball)"

# Turn .../icons/hicolor/48x48/apps/image-swiper.png into hicolor/48x48/apps/image-swiper.png.
# Done with basename/dirname rather than a ${var#prefix} expansion so that a
# checkout path containing glob characters cannot confuse the pattern match.
icon_relpath() {
    size=$(basename -- "$(dirname -- "$(dirname -- "$1")")")
    printf 'hicolor/%s/apps/%s\n' "$size" "$(basename -- "$1")"
}

update_caches() {
    # Only useful outside a staging directory, and only for real icon themes and
    # desktop-entry directories: without hicolor/index.theme the icon cache tool
    # would create a theme of its own.
    [ -z "$DESTDIR" ] || return 0
    if [ -f "$ICONS_DIR/hicolor/index.theme" ] && command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t "$ICONS_DIR/hicolor" || true
    fi
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q "$APPLICATIONS_DIR" || true
    fi
}

if [ "$UNINSTALL" -eq 1 ]; then
    removed=0
    if [ -f "$APPLICATIONS_DIR/image-swiper.desktop" ]; then
        rm -f "$APPLICATIONS_DIR/image-swiper.desktop"
        removed=$((removed + 1))
    fi
    if [ -d "$ICONS_SRC/hicolor" ]; then
        for icon in "$ICONS_SRC"/hicolor/*/apps/image-swiper.*; do
            [ -e "$icon" ] || continue
            target="$ICONS_DIR/$(icon_relpath "$icon")"
            if [ -e "$target" ]; then
                rm -f "$target"
                removed=$((removed + 1))
            fi
        done
    fi
    rmdir "$APPLICATIONS_DIR" 2>/dev/null || true
    if [ -d "$ICONS_DIR/hicolor" ]; then
        # Drop the per-size directories this script owns, then hicolor itself
        # when nothing else lives there. Only empty directories are removed.
        for dir in "$ICONS_DIR"/hicolor/*/apps "$ICONS_DIR"/hicolor/* "$ICONS_DIR"/hicolor; do
            if [ -d "$dir" ]; then
                rmdir "$dir" 2>/dev/null || true
            fi
        done
    fi
    update_caches
    printf 'Removed %s file(s) from %s\n' "$removed" "$DATA_ROOT"
    exit 0
fi

install -D -m 644 "$DATA_FILE" "$APPLICATIONS_DIR/image-swiper.desktop"
installed=1
for icon in "$ICONS_SRC"/hicolor/*/apps/image-swiper.*; do
    [ -e "$icon" ] || continue
    install -D -m 644 "$icon" "$ICONS_DIR/$(icon_relpath "$icon")"
    installed=$((installed + 1))
done

update_caches

printf 'Installed %s file(s) into %s\n' "$installed" "$DATA_ROOT"
printf 'Desktop entry: %s\n' "$APPLICATIONS_DIR/image-swiper.desktop"
if ! command -v image-swiper >/dev/null 2>&1; then
    printf 'note: `image-swiper` is not on PATH yet; install the package first (pip install .) so the launcher can start it\n'
fi
