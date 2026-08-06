# Environment Variables

This project has separate database URLs for runtime traffic and migrations.
Keep real secret values only in the deployment provider environment stores.

## Database URL Rules

`DATABASE_URL` is owned by the backend runtime and must use the async SQLAlchemy
driver: `postgresql+asyncpg://`.

`MIGRATION_DATABASE_URL` is owned by Alembic migrations and must use the sync
SQLAlchemy driver: `postgresql+psycopg://`.

Hosted database URLs should use driver-specific TLS query parameters:
runtime asyncpg URLs use `?ssl=require`, while migration psycopg URLs use
`?sslmode=require`. Do not put psycopg-only `sslmode` or `channel_binding`
query parameters on `DATABASE_URL`; SQLAlchemy forwards them to asyncpg as
unsupported connection kwargs. Alembic does not derive its URL from
`DATABASE_URL`.

`NEXT_PUBLIC_BACKEND_URL` is frontend-only Vercel configuration. Do not add it
as a required backend secret.

## Backend And Migration Variables

| Variable                           | Required                                       | Secret/Public      | Owner                    | Default                                                  | Valid example                                                                                                  |
| ---------------------------------- | ---------------------------------------------- | ------------------ | ------------------------ | -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `APP_NAME`                       | Optional                                       | Private non-secret | Backend API              | `RAG Docs Pipeline`                                    | `RAG Docs Pipeline`                                                                                          |
| `ENVIRONMENT`                    | Required in production                         | Private non-secret | Backend API              | `local`                                                | `production`                                                                                                 |
| `API_PREFIX`                     | Optional                                       | Private non-secret | Backend API              | `/api`                                                 | `/api`                                                                                                       |
| `ADMIN_SECRET`                   | Required in production                         | Secret             | Backend API              | Empty                                                    | `example-admin-secret-change-me`                                                                             |
| `QUERY_RATE_LIMIT_PER_MINUTE`    | Optional                                       | Private non-secret | Backend API              | `20`                                                   | `20`                                                                                                         |
| `FEEDBACK_RATE_LIMIT_PER_MINUTE` | Optional                                       | Private non-secret | Backend API              | `30`                                                   | `30`                                                                                                         |
| `SYNC_RATE_LIMIT_PER_MINUTE`     | Optional                                       | Private non-secret | Backend API              | `2`                                                    | `2`                                                                                                          |
| `DATABASE_URL`                   | Required in production                         | Secret             | Backend API runtime      | `postgresql+asyncpg://rag:rag@localhost:5432/rag_docs` | `postgresql+asyncpg://app_user:example_password@ep-example.us-east-2.aws.neon.tech/rag_docs?ssl=require`     |
| `MIGRATION_DATABASE_URL`         | Required in production                         | Secret             | Alembic migration job    | `postgresql+psycopg://rag:rag@localhost:5432/rag_docs` | `postgresql+psycopg://app_user:example_password@ep-example.us-east-2.aws.neon.tech/rag_docs?sslmode=require` |
| `GITHUB_TOKEN`                   | Optional                                       | Secret             | Backend ingestion        | Empty                                                    | `github_pat_example_token`                                                                                   |
| `GITHUB_USER_AGENT`              | Optional                                       | Private non-secret | Backend ingestion        | `rag-docs-pipeline`                                    | `rag-docs-pipeline`                                                                                          |
| `HTTP_TIMEOUT_SECONDS`           | Optional                                       | Private non-secret | Backend API              | `30.0`                                                 | `30.0`                                                                                                       |
| `HTTP_MAX_RETRIES`               | Optional                                       | Private non-secret | Backend API              | `2`                                                    | `2`                                                                                                          |
| `HTTP_RETRY_BACKOFF_SECONDS`     | Optional                                       | Private non-secret | Backend API              | `0.5`                                                  | `0.5`                                                                                                        |
| `EMBEDDING_PROVIDER`             | Optional                                       | Private non-secret | Backend retrieval        | `local`                                                | `openai`                                                                                                     |
| `EMBEDDING_DIMENSIONS`           | Optional                                       | Private non-secret | Backend retrieval        | `1536`                                                 | `1536`                                                                                                       |
| `OPENAI_API_KEY`                 | Required only when OpenAI features are enabled | Secret             | Backend AI providers     | Empty                                                    | `openai-example-key-not-real`                                                                                |
| `OPENAI_EMBEDDING_MODEL`         | Optional                                       | Private non-secret | Backend retrieval        | `text-embedding-3-small`                               | `text-embedding-3-small`                                                                                     |
| `LLM_PROVIDER`                   | Optional                                       | Private non-secret | Backend answer synthesis | `extractive`                                           | `extractive`                                                                                                 |
| `RETRIEVAL_MIN_SCORE`            | Optional                                       | Private non-secret | Backend retrieval        | `0.0`                                                  | `0.2`                                                                                                        |
| `RETRIEVAL_MIN_FUSED_SCORE`      | Optional                                       | Private non-secret | Backend retrieval        | `0.0`                                                  | `0.05`                                                                                                       |
| `RETRIEVAL_MIN_SCORE_GAP`        | Optional                                       | Private non-secret | Backend retrieval        | `0.0`                                                  | `0.01`                                                                                                       |
| `RETRIEVAL_CANDIDATE_K`          | Optional                                       | Private non-secret | Backend retrieval        | `50`                                                   | `50`                                                                                                         |
| `RETRIEVAL_RRF_K`                | Optional                                       | Private non-secret | Backend retrieval        | `60`                                                   | `60`                                                                                                         |
| `RETRIEVAL_VECTOR_WEIGHT`        | Optional                                       | Private non-secret | Backend retrieval        | `0.7`                                                  | `0.7`                                                                                                        |
| `RETRIEVAL_TEXT_WEIGHT`          | Optional                                       | Private non-secret | Backend retrieval        | `0.3`                                                  | `0.3`                                                                                                        |
| `ALLOWED_ORIGINS`                | Required for deployed frontend access          | Public             | Backend API CORS         | `["http://localhost:3000","http://127.0.0.1:3000"]`    | `["https://docs-chat.example.com"]`                                                                          |

## Frontend Variables

| Variable                    | Required                                                             | Secret/Public | Owner             | Default                 | Valid example                   |
| --------------------------- | -------------------------------------------------------------------- | ------------- | ----------------- | ----------------------- | ------------------------------- |
| `NEXT_PUBLIC_BACKEND_URL` | Required when the frontend cannot use its built-in local backend URL | Public        | Frontend (Vercel) | Frontend local fallback | `https://rag-api.example.com` |
