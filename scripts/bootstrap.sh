#!/bin/sh
# Put Budgie and gitboard in apps/ (clone only; the Makefile install does the rest).
# Safe to re-run: an app already in apps/ is left exactly as it is.
set -eu
PERCH_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BUDGIE_URL=https://github.com/adamsrnmsu/budgie.git
GB_URL=https://github.com/adamsrnmsu/remote-gitboard.git

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
