version: "3.9"

services:

  # --------------------------------------------------
  # PostgreSQL - System of Record
  # --------------------------------------------------
  postgres:
    image: postgres:15
    container_name: rag-postgres
    restart: always
    environment:
      POSTGRES_DB: ragdb
      POSTGRES_USER: raguser
      POSTGRES_PASSWORD: ragpass
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U raguser -d ragdb"]
      interval: 10s
      timeout: 5s
      retries: 5


  # --------------------------------------------------
  # Weaviate - Vector Database
  # --------------------------------------------------
  weaviate:
    image: semitechnologies/weaviate:1.24.1
    container_name: rag-weaviate
    restart: always
    ports:
      - "8080:8080"
    environment:
      QUERY_DEFAULTS_LIMIT: 25
      AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED: "true"
      PERSISTENCE_DATA_PATH: "/var/lib/weaviate"
      DEFAULT_VECTORIZER_MODULE: "text2vec-transformers"
      ENABLE_MODULES: "text2vec-transformers"
      TRANSFORMERS_INFERENCE_API: "http://transformers:8080"
      CLUSTER_HOSTNAME: "node1"
    depends_on:
      - transformers
    volumes:
      - weaviate_data:/var/lib/weaviate


  # --------------------------------------------------
  # Transformers - Embedding Model (Local, No LLM)
  # --------------------------------------------------
  transformers:
    image: semitechnologies/transformers-inference:sentence-transformers-all-MiniLM-L6-v2
    container_name: rag-transformers
    restart: always
    ports:
      - "8081:8080"
    environment:
      ENABLE_CUDA: "0"   # set 1 if you have GPU


  # --------------------------------------------------
  # RAG API - Unified /query + /compare
  # --------------------------------------------------
  rag-api:
    image: python:3.11-slim
    container_name: rag-api
    restart: always
    working_dir: /app
    volumes:
      - ./rag_api.py:/app/rag_api.py
    command: >
      sh -c "pip install fastapi uvicorn psycopg2-binary weaviate-client &&
             uvicorn rag_api:app --host 0.0.0.0 --port 9000"
    ports:
      - "9000:9000"
    environment:
      PG_HOST: postgres
      PG_DB: ragdb
      PG_USER: raguser
      PG_PASSWORD: ragpass
      WEAVIATE_URL: http://weaviate:8080
    depends_on:
      postgres:
        condition: service_healthy
      weaviate:
        condition: service_started


  # --------------------------------------------------
  # LibreChat RAG Middleware
  # --------------------------------------------------
  rag-middleware:
    image: python:3.11-slim
    container_name: rag-middleware
    restart: always
    working_dir: /app
    volumes:
      - ./librechat_rag_middleware.py:/app/librechat_rag_middleware.py
    command: >
      sh -c "pip install fastapi uvicorn requests &&
             uvicorn librechat_rag_middleware:app --host 0.0.0.0 --port 9100"
    ports:
      - "9100:9100"
    environment:
      RAG_QUERY_URL: http://rag-api:9000/query
      DEFAULT_PROJECT: AMBOSELI
    depends_on:
      - rag-api


volumes:
  pgdata:
  weaviate_data: