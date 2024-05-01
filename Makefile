PWD = $(shell pwd)
REPO_ROOT = $(abspath $(PWD)/..)

VENV = $(PWD)/env
BIN_AUTOPEP8 = $(VENV)/bin/autopep8
BIN_ISORT = $(VENV)/bin/isort
BIN_MYPY = $(VENV)/bin/mypy
BIN_PIP = $(VENV)/bin/pip
BIN_PYLINT = $(VENV)/bin/pylint
BIN_PYTEST = $(VENV)/bin/pytest
BIN_PYTHON = $(VENV)/bin/python


PYLINT_EXTRA_ARGS ?=
PYTEST_ARGS =
PYTEST_NUM_PROCESSES ?= auto
PYTHON_VERSION ?= "python3.11"
REQUIREMENTS_FILE ?= $(PWD)/requirements.txt
TEST_TARGETS ?= tests


.DEFAULT_GOAL := build


.PHONY = autopep8 autopep8_diff build build_pypi check_dependencies clean help isort isort_check isort_diff mypy pylint test test_continuous wheel wheel_clean

## Run autopep8 against the package
autopep8:
	"$(BIN_AUTOPEP8)" --in-place --recursive .

## Print a diff of the changes that autopep8 would make
autopep8_diff:
	"$(BIN_AUTOPEP8)" --diff --exit-code --recursive .

build:
	"$(PWD)/setup.sh" \
		--no-use-pypi \
		--no-use-system-thrift-compiler \
		--python-version $(PYTHON_VERSION) \
		--requirements-path $(REQUIREMENTS_FILE) \
		--setup-thirdparty-binaries \
	        --venv-dir $(VENV)

build_pypi:
	"$(PWD)/setup.sh" \
		--no-use-system-thrift-compiler \
		--python-version $(PYTHON_VERSION) \
		--requirements-path $(REQUIREMENTS_FILE) \
		--venv-dir $(VENV)

build_jenkins:
	"$(PWD)/setup.sh" \
		--python-version $(PYTHON_VERSION) \
		--requirements-path $(REQUIREMENTS_FILE) \
		--thrift-types-path $(PWD)/thrift_types \
		--use-system-thrift-compiler \
	        --venv-dir $(VENV)

check_dependencies:
	"$(BIN_PIP)" check

clean: wheel_clean
	rm -rf $(VENV) src/*/__pycache__

# From https://gist.github.com/prwhite/8168133
help:
	@echo ''
	@echo 'Usage:'
	@echo '  ${YELLOW}make${RESET} ${GREEN}<target>${RESET}'
	@echo ''
	@echo 'Targets:'
	@awk '/^[a-zA-Z\-\_0-9]+:/ { \
		helpMessage = match(lastLine, /^## (.*)/); \
		if (helpMessage) { \
			helpCommand = $$1; sub(/:$$/, "", helpCommand); \
			helpMessage = substr(lastLine, RSTART + 3, RLENGTH); \
			printf "  ${YELLOW}%-$(TARGET_MAX_CHAR_NUM)s${RESET} ${GREEN}%s${RESET}\n", helpCommand, helpMessage; \
		} \
	} \
	{ lastLine = $$0 }' $(MAKEFILE_LIST)

isort:
	"$(BIN_ISORT)" .

isort_check:
	"$(BIN_ISORT)" --check-only .

isort_diff:
	"$(BIN_ISORT)" --diff .

mypy:
	"$(BIN_MYPY)"  \
		--config-file=mypy.ini \
		src/ tests/

pylint:
	"$(BIN_PYLINT)" -j 0 \
	    -rn \
	    --ignore=src/lib.egg-info \
	    $(PYLINT_EXTRA_ARGS) \
	    src/* tests/*

## Execute unittests.
test: PYTEST_ARGS += --numprocesses=$(PYTEST_NUM_PROCESSES)
test: $(BIN_PYTEST)
test:
	"$(BIN_PYTEST)" $(PYTEST_ARGS) $(TEST_TARGETS)

# Continuous testing uses the following pytest args:
# --color=yes: By default `looponfail` disables the color for pytest's output. This flag re-enables
#    the color.
# --exitfirst: Stop the test run after hitting the first failure.
# --failed-first: On subsequent runs of pytest, run the test cases that failed during the last run
#     first.
# --looponfail: Run the tests once. Then, rerun tests anytime the package's files are modified.
#
# The exitfirst and failed-first commands only work when using a single process to execute
# tests. Thus, we set the number of processes to `0` when using test_continuous.
#
# To change which test cases to target, set the TEST_TARGETS variable when running make:
#     make test_continuous TEST_TARGETS=<test_file>::<test_class_name>::<test_case_name>
#
## Continuously execute unittests.
test_continuous: PYTEST_NUM_PROCESSES = 0
test_continuous: PYTEST_ARGS += --color=yes
test_continuous: PYTEST_ARGS += --exitfirst
test_continuous: PYTEST_ARGS += --failed-first
test_continuous: PYTEST_ARGS += --looponfail
test_continuous: test

wheel:
	"$(BIN_PYTHON)" setup.py sdist bdist_wheel

wheel_clean:
	rm -rf build dist src/*.egg-info
