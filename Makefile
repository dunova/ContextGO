.PHONY: install test lint format smoke health bench clean

install:
	pip install -e ".[dev]"

test:
	python3 -m pytest scripts/test_context_cli.py scripts/test_context_core.py \
		scripts/test_context_native.py scripts/test_context_smoke.py \
		scripts/test_session_index.py scripts/test_autoresearch_contextgo.py -v

lint:
	ruff check scripts/ benchmarks/
	ruff format --check scripts/ benchmarks/

format:
	ruff format scripts/ benchmarks/
	ruff check --fix scripts/ benchmarks/

smoke:
	python3 scripts/context_cli.py smoke

health:
	python3 scripts/context_cli.py health

bench:
	python3 -m benchmarks --mode both --iterations 1 --warmup 0 --query benchmark --format text

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
