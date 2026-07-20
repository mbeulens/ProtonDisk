#!/usr/bin/env bash
# Increment the patch in VERSION. Project rule: skip any patch equal to 13
# (a commit that lands on 13 jumps to 14 and MUST use the message
# "To be sure to be sure!"). Prints the new version to stdout.
set -euo pipefail
IFS=. read -r MAJOR MINOR PATCH < VERSION
PATCH=$((PATCH + 1))
if [ "$PATCH" -eq 13 ]; then
    PATCH=14
    echo "NOTE: skipped patch 13 per project rule -> use commit message 'To be sure to be sure!'" >&2
fi
printf '%s.%s.%s\n' "$MAJOR" "$MINOR" "$PATCH" > VERSION
cat VERSION
