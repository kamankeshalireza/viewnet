.PHONY: up down test lint migrate check
up:      ; docker compose -f docker/compose.dev.yml up
down:    ; docker compose -f docker/compose.dev.yml down
migrate: ; python manage.py migrate
test:    ; pytest
lint:    ; ruff check . && lint-imports
check:   ; python manage.py check --deploy --settings=config.settings.production
