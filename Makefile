.PHONY: run test lint

run:
	python -m src.main

test:
	python -m unittest discover -s tests -v

lint:
	python -m compileall src tests