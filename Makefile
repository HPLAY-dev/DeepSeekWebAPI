.PHONY: help install test clean docs

help:
	@echo "Available commands:"
	@echo "  install    Install dependencies"
	@echo "  test       Run tests"
	@echo "  clean      Clean build files"
	@echo "  docs       Build documentation"

install:
	pip install -r requirements.txt
	pip install -e .

test:
	python -m unittest discover tests

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/

docs:
	cd docs && make html