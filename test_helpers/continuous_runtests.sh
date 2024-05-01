#! /bin/bash
set -euo pipefail
IFS=$'\n\t'

function usage() {
    echo "Usage: continuous_runtests.sh <path> [--with-coverage]"
    echo "  <path>: The path to a file or directory that will be tested (e.g. web_api/handlers/web_test.py or web_api/handlers). The path can contian specific modules or tests to run. For example:"
    echo "      <path>::TestClass"
    echo "      <path>::TestClass::test_method"
    echo "  --with-coverage: Generates a code coverage report after every run. The coverage report can be accessed by opening a browser and going to <pwd>/htmlcov/index.html."
    exit 1
}

if [ "$#" -eq 0 ]; then
    usage
fi

TEST_CMD="$1"
# Shift the first argument off the stack (we don't need it anymore).
shift
# Verify that the TEST_CMD references a python file.
if [[ "$TEST_CMD" != *".py"* ]]; then
    usage
fi


PYTEST_CMD=("pytest" "--ignore" "\..*" "--ff" "-x" "$TEST_CMD")
for var in "$@"; do
    case "$var" in
        --with-coverage)
            PYTEST_CMD+=("--cov" "--cov-report" "html" "--cov-branch")
            shift 1
            ;;
    esac
done


if ! command -v entr > /dev/null; then
    echo "The 'entr' command is required to use continuous_runtests.sh."
    echo "Install 'entr' with 'brew install entr', or download from http://entrproject.org/."
    exit 1
fi


BASEDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
TEST_PATH=${TEST_CMD%%::*}

# Ignore hidden files that start with ".".
# --ff: On subsequent runs of pytest, run the test cases that failed during the last run first.
# -x: Stops after the first failure.
python "$BASEDIR/find_dependencies.py" --path="$TEST_PATH" | entr "${PYTEST_CMD[@]}" "$@"
