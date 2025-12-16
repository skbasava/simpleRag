#!/usr/bin/env bash
set -euo pipefail

#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: ./build-service.sh <service-name>"
  exit 1
fi

SERVICE=$1
COMPOSE="docker compose"

echo "======================================"
echo "🔨 Building service: $SERVICE"
echo "======================================"

# Build only the requested service
$COMPOSE build "$SERVICE"

# Start dependencies automatically
echo "▶️  Starting $SERVICE..."
$COMPOSE up -d "$SERVICE"

echo "✅ Service '$SERVICE' is up"





echo "======================================"
echo "🚀 Building RAG system"
echo "======================================"

COMPOSE="docker compose"

# --------------------------------------------------
# Step 1: Clean old state (optional but recommended)
# --------------------------------------------------
echo "🧹 Stopping old containers..."
$COMPOSE down --remove-orphans

# --------------------------------------------------
# Step 2: Build images
# --------------------------------------------------
echo "🔨 Building images..."
$COMPOSE build

# --------------------------------------------------
# Step 3: Start infrastructure first
# --------------------------------------------------
echo "🧱 Starting Postgres + Weaviate..."
$COMPOSE up -d postgres weaviate

# --------------------------------------------------
# Step 4: Wait for health checks
# --------------------------------------------------
echo "⏳ Waiting for services to become healthy..."

wait_for_service () {
  local service=$1
  local retries=30
  local count=0

  while [ $count -lt $retries ]; do
    status=$($COMPOSE ps --format json | jq -r \
      ".[] | select(.Service==\"$service\") | .Health")

    if [ "$status" == "healthy" ]; then
      echo "✅ $service is healthy"
      return
    fi

    sleep 2
    count=$((count+1))
  done

  echo "❌ $service did not become healthy in time"
  exit 1
}

wait_for_service postgres
wait_for_service weaviate

# --------------------------------------------------
# Step 5: Run ingestion job (one-time)
# --------------------------------------------------
echo "📥 Running ingestion job..."
$COMPOSE up --abort-on-container-exit rag-ingestion

# --------------------------------------------------
# Step 6: Start API + Chainlit
# --------------------------------------------------
echo "🌐 Starting API + Chainlit..."
$COMPOSE up -d rag-api chainlit

echo "======================================"
echo "✅ RAG system is up and running"
echo "======================================"

echo "API:       http://localhost:8000"
echo "Chainlit:  http://localhost:8501"