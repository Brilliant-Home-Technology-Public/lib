#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

PYTHON="python3.8"

BASEDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VENV_DIR="$BASEDIR/env"
REQUIREMENTS_PATH="$BASEDIR/requirements.txt"
THRIFT_TYPES_PATH="$BASEDIR/../thrift_types"
THRIFT_COMPILER_PATH="/usr/local/bin/thrift"
SETUP_THIRDPARTY_BINARIES=false
USE_PYPI=true

while [ $# -gt 0 ]; do
    case "${1}" in
    --no-setup-thirdparty-binaries)
        SETUP_THIRDPARTY_BINARIES=false
        shift 1
        ;;
    --no-use-pypi)
        USE_PYPI=false
        shift 1
        ;;
    --no-use-system-thrift-compiler)
        THRIFT_COMPILER_PATH="$BASEDIR/../thirdparty-binaries/pre-built/current_platform/thrift/bin/thrift"
        shift 1
        ;;
    --python-version)
        PYTHON="${2}"
        shift 2
        ;;
    --requirements-path)
        REQUIREMENTS_PATH="${2}"
        shift 2
        ;;
    --setup-thirdparty-binaries)
        SETUP_THIRDPARTY_BINARIES=true
        shift 1
        ;;
    --thrift-types-path)
        THRIFT_TYPES_PATH="${2}"
        shift 2
        ;;
    --use-pypi)
        USE_PYPI=true
        shift 1
        ;;
    --use-system-thrift-compiler)
        THRIFT_COMPILER_PATH="/usr/local/bin/thrift"
        shift 1
        ;;
    --venv-dir)
        VENV_DIR="${2}"
        shift 2
        ;;
    *)
        echo >&2 "Unrecognized parameter ${1}"
        ;;
    esac
done

BIN_PIP="$VENV_DIR/bin/pip"
BIN_PYTHON="$VENV_DIR/bin/python"

if [[ "$SETUP_THIRDPARTY_BINARIES" == "true" ]]; then
    $("$BASEDIR/../thirdparty-binaries/setup.sh")
fi

"$PYTHON" -m venv "$VENV_DIR"

# Build thrift before trying to install the thrift-types package
make THRIFT_COMPILER="$THRIFT_COMPILER_PATH" -j4 -C "$THRIFT_TYPES_PATH/python"

"$BIN_PIP" install -U pip==22.3.1

# Installing wheel allows the pip cache to store wheels locally.
"$BIN_PIP" install wheel
if [[ "$USE_PYPI" == "false" ]] && [[ -d "$BASEDIR/../thirdparty-binaries/python/wheels" ]]; then
    "$BIN_PIP" install \
        --no-cache-dir \
        --no-index \
        --find-links="$BASEDIR/../thirdparty-binaries/python/wheels" \
        --requirement="$REQUIREMENTS_PATH"
else
    # The --only-binary flag forces pip to install wheels only. We force wheels only so that pip
    # doesn't need to download and install the package from source, which should decrease install
    # time. Thus, when upgrading a requirement, you must make sure that the wheel exists on our
    # private server, otherwise setup will fail.
    "$BIN_PIP" install \
        --index-url=https://pypi.internal.brilliant.tech/simple \
        --only-binary=:all: \
        --requirement="$REQUIREMENTS_PATH"
fi

# Install thrift_types here since the location of thrift_types will change based on the
# repo/Jenkins.
"$BIN_PIP" install -e "$THRIFT_TYPES_PATH/python"
"$BIN_PIP" install -e ./[all]
