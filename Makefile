.PHONY: install check lint fmt test

install:  ## install the package with dev tools
	pip install -e ".[dev]"

lint:  ## ruff lint
	ruff check .

fmt:  ## auto-format + fix
	ruff format .
	ruff check --fix .

test:  ## run the test suite
	pytest -q

check: lint test  ## what CI runs
