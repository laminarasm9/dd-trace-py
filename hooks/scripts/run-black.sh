#!/bin/sh
staged_files=$(git diff --staged --name-only HEAD --diff-filter=ACMR | grep -E '\.py$')
if [ -z "$staged_files" ]; then
    riot -v run -s black $staged_files
else
    echo 'Run black skipped: No Python files were found in `git diff --staged`'
fi

