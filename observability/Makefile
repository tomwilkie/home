HAOS_HOST        := root@homeassistant.local
HAOS_DIR         := /homeassistant/alloy
HAOS_DIR_HOST    := /mnt/data/supervisor/homeassistant/alloy
DOCKER_HOST      := ssh://$(HAOS_HOST)

export DOCKER_HOST

.PHONY: deploy up down restart logs ps shell

deploy: push up

push:
	ssh $(HAOS_HOST) "mkdir -p $(HAOS_DIR)"
	ssh $(HAOS_HOST) "cat > $(HAOS_DIR)/config.alloy" < alloy/config.alloy

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart alloy

logs:
	docker compose logs --tail=100 alloy

ps:
	docker compose ps

shell:
	docker compose exec alloy bash
