COMPOSE = docker compose

.PHONY: help build destroy clean logs ps \
        api ingest chainlit postgres weaviate \
        build-api build-ingest build-chainlit

help:
	@echo ""
	@echo "System:"
	@echo "  make build            → Build & start full system"
	@echo "  make destroy          → Stop system safely"
	@echo ""
	@echo "Build individual services:"
	@echo "  make build-api        → Build rag-api only"
	@echo "  make build-ingest     → Build ingestion job only"
	@echo "  make build-chainlit   → Build chainlit only"
	@echo ""
	@echo "Run individual services:"
	@echo "  make api              → Start rag-api"
	@echo "  make ingest           → Run ingestion job"
	@echo "  make chainlit         → Start chainlit"
	@echo "  make postgres         → Start postgres"
	@echo "  make weaviate         → Start weaviate"
	@echo ""

# -------------------------
# Full system
# -------------------------

build:
	./build.sh

destroy:
	./destroy.sh

clean:
	$(COMPOSE) down -v --remove-orphans

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

# -------------------------
# Build individual services
# -------------------------

build-api:
	$(COMPOSE) build rag-api

build-ingest:
	$(COMPOSE) build rag-ingestion

build-chainlit:
	$(COMPOSE) build chainlit

# -------------------------
# Run individual services
# -------------------------

api:
	$(COMPOSE) up -d rag-api

ingest:
	$(COMPOSE) up --abort-on-container-exit rag-ingestion

chainlit:
	$(COMPOSE) up -d chainlit

postgres:
	$(COMPOSE) up -d postgres

weaviate:
	$(COMPOSE) up -d weaviate