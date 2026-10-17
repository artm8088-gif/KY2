#!/usr/bin/env bash
#python3 -m src.main --package express --repo https://github.com/expressjs/express
set -e


echo ""
echo "=== Проверка ручного сценария (test-mode) ==="
python3 -m src.main --package requests --repo ./tests/fixtures/package.json --test-mode