HAOS_HOST        := root@homeassistant.local
HAOS_DIR         := /homeassistant/alloy
HAOS_DIR_HOST    := /mnt/data/supervisor/homeassistant/alloy
DOCKER_HOST      := ssh://$(HAOS_HOST)

# UniFi-Poller dashboards deployed from the unpoller/dashboards submodule
UNPOLLER_DIR     := dashboards/unpoller/v2.0.0
UNPOLLER_FOLDER  := fwvr7h
UNPOLLER_DS      := grafanacloud-prom
UNPOLLER_BOARDS  := Client UAP UMBB USG USW

export DOCKER_HOST

.PHONY: deploy up down restart logs ps shell unpoller-dashboards

deploy: push up

push:
	ssh $(HAOS_HOST) "mkdir -p $(HAOS_DIR)"
	ssh $(HAOS_HOST) "cat > $(HAOS_DIR)/config.alloy" < alloy/config.alloy

up: .env
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

.env:
	op environment read kq66m26rzkq7ad23i2zmjuchia >.env

unpoller-dashboards:
	@for board in $(UNPOLLER_BOARDS); do \
	  file="$(UNPOLLER_DIR)/UniFi-Poller_ $$board Insights - Prometheus.json"; \
	  tmp=$$(mktemp); \
	  jq --arg ds "$(UNPOLLER_DS)" --arg folder "$(UNPOLLER_FOLDER)" \
	    '{dashboard: (walk(if type == "string" then gsub("\\$$\\{DS_[A-Z_]+\\}"; $$ds) else . end) | del(.id, .__inputs, .__requires, .__elements)), folderUid: $$folder, overwrite: true, message: "unpoller/dashboards"}' \
	    "$$file" > "$$tmp" || { rm -f "$$tmp"; exit 1; }; \
	  result=$$(gcx api /api/dashboards/db -d @"$$tmp" 2>/dev/null); rm -f "$$tmp"; \
	  echo "$$result" | jq -e -r 'select(.status == "success") | "\(.status) \(.url)"' || { echo "upload failed: $$board"; exit 1; }; \
	done
