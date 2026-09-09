.PHONY: setup test run

setup:
	python -m venv .venv && .venv/bin/pip install -r requirements.txt

test:
	.venv/bin/pytest -q

run:
	.venv/bin/python -m src.main "$(P)"
