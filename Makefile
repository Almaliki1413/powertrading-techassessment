.PHONY: bootstrap dev test lint build run verify-data

bootstrap:
	python scripts/make.py bootstrap

dev:
	python scripts/make.py dev

test:
	python scripts/make.py test

lint:
	python scripts/make.py lint

build:
	python scripts/make.py build

run:
	python scripts/make.py run

verify-data:
	python scripts/make.py verify-data
