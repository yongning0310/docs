.PHONY: install dev test lint clean reset perf db-up db-down db-wait

db-up:
	docker compose up -d
	@$(MAKE) db-wait

db-down:
	docker compose down

db-wait:
	@echo "Waiting for PostgreSQL..."
	@until docker compose exec -T db pg_isready -U postgres -q 2>/dev/null; do sleep 0.5; done
	@echo "PostgreSQL is ready."

install:
	pip install -r requirements.txt

dev: db-up
	uvicorn app.main:app --reload --port 8000

test: db-up
	pytest tests/ -v

lint:
	python -m py_compile app/main.py
	python -m py_compile app/config.py
	python -m py_compile app/database.py
	python -m py_compile app/models.py
	python -m py_compile app/errors.py
	python -m py_compile app/seed.py
	python -m py_compile app/services/redline.py
	python -m py_compile app/services/search.py
	python -m py_compile app/services/embeddings.py
	python -m py_compile app/services/llm.py
	python -m py_compile app/routers/documents.py
	python -m py_compile app/routers/search.py
	python -m py_compile app/routers/suggestions.py

clean:
	docker compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

perf: db-up
	python benchmarks/run.py
	python benchmarks/plot.py

reset: clean db-up dev
