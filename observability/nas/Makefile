NAS_HOST := twilkie@NAS.local
NAS_DIR  := /volume3/docker/alloy
# The sudoers rule allows this one binary without a password
DOCKER   := sudo -n /usr/local/bin/docker
COMPOSE  := ssh $(NAS_HOST) "cd $(NAS_DIR) && $(DOCKER) compose

# The HAOS host's 1Password Environment, with the SNMP credentials added
OP_ENV   := kq66m26rzkq7ad23i2zmjuchia
ENV_VARS := STACK_NAME|ACCESS_TOKEN|SNMP_USERNAME|SNMP_PASSWORD

.PHONY: deploy push up down restart logs ps

deploy: push up

push: .env
	ssh $(NAS_HOST) "mkdir -p $(NAS_DIR) && chmod 700 $(NAS_DIR)"
	ssh $(NAS_HOST) "cat > $(NAS_DIR)/docker-compose.yml" < docker-compose.yml
	ssh $(NAS_HOST) "cat > $(NAS_DIR)/config.alloy" < config.alloy
	ssh $(NAS_HOST) "umask 077 && cat > $(NAS_DIR)/.env" < .env

up:
	$(COMPOSE) up -d"

down:
	$(COMPOSE) down"

restart:
	$(COMPOSE) restart alloy"

logs:
	$(COMPOSE) logs --tail=100 alloy"

ps:
	$(COMPOSE) ps"

.env:
	op environment read $(OP_ENV) | grep -E '^($(ENV_VARS))=' >.env
