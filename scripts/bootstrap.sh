#!/bin/sh
# Put Budgie and gitboard in apps/, then install and link all three.
# Safe to re-run: an app already in apps/ is left exactly as it is.
#   BUDGIE_URL=... GB_URL=...   clone from somewhere else
#   BOOTSTRAP_NO_INSTALL=1      clone only (the tests use this)
set -eu
PERCH_DIR=$(cd "$(dirname "$0")/.." && pwd)
BUDGIE_URL=${BUDGIE_URL:-git@github.com:adamsrnmsu/budgie.git}
GB_URL=${GB_URL:-https://github.com/adamsrnmsu/remote-gitboard.git}

fail() { echo "bootstrap: $*" >&2; exit 1; }

fetch() {  # fetch NAME URL
    dir="$PERCH_DIR/apps/$1"
    if [ -d "$dir/.git" ]; then
        echo "apps/$1: already there, left alone"
    elif [ -e "$dir" ]; then
        fail "apps/$1 exists but is not a git checkout; move it away and re-run"
    else
        echo "apps/$1: cloning $2"
        git clone -q "$2" "$dir" || fail "cloning $1 from $2 failed"
    fi
}

mkdir -p "$PERCH_DIR/apps"
fetch budgie "$BUDGIE_URL"
fetch remote-gitboard "$GB_URL"
if [ -z "${BOOTSTRAP_NO_INSTALL:-}" ]; then
    make -C "$PERCH_DIR" install link || fail "make install link failed"
fi
echo
echo "Put this line in your workspace's perch-home.yaml:"
echo "gitboard_dir: $PERCH_DIR/apps/remote-gitboard"
