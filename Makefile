

```makefile
.PHONY: run install test lint clean stage2

# Запуск приложения (пример: make run ARGS="--package express --repo https://github.com/expressjs/express")
run:
	./run.sh $(ARGS)

# Установка/обновление зависимостей
install:
	pip install -r requirements.txt

# Запуск тестов (pytest)
test:
	.venv/bin/python -m pytest tests/ -v

# Проверка Этапа 2 (тесты + ручной вывод локальной фикстуры)
stage2:
	./test_stage2.sh

# Линтинг (если установлен ruff/flake8, опционально)
lint:
	.venv/bin/python -m ruff check src/ || true

# Очистка временных файлов
clean:
	rm -rf .venv __pycache__ src/__pycache__ tests/__pycache__ .pytest_cache
	find . -name '*.pyc' -delete