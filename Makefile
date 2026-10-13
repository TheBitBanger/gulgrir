COMPOSE := docker compose --env-file .env -f compose/dev.yml -f compose/dev.bind.yml

.PHONY: dev-build dev-up check smoke-test-image

dev-build:
	$(COMPOSE) up -d --build db app

dev-up:
	$(COMPOSE) up -d db app

check:
	@$(COMPOSE) --progress quiet up -d db app
	@$(COMPOSE) exec -T -w /workspace app bash scripts/check.sh

smoke-test-image:
	@bash scripts/smoke-test-image.sh
