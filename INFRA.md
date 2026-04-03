# Production Infrastructure

How to turn the Redline Service prototype into a production-grade system.

## Architecture

```
            Users
              │
       ┌──────┴──────┐
       │  CloudFront  │  ← static assets, cached search results (short TTL)
       └──────┬──────┘
       ┌──────┴──────┐
       │    ALB      │  ← TLS 1.3 termination, JWT validation
       └──────┬──────┘
              │
    ┌─────────┼─────────┐
    │         │         │
┌───┴───┐ ┌──┴──┐ ┌────┴──┐
│  ECS  │ │ ECS │ │  ECS  │  ← Fargate, auto-scale on CPU/request count
│Fargate│ │ ... │ │  ...  │     stateless, 0.5 vCPU / 1GB each
└───┬───┘ └──┬──┘ └────┬──┘
    │        │         │
    ├────────┼─────────┤
    │        │         │
┌───┴──┐ ┌──┴───┐ ┌───┴──┐ ┌────────┐
│  RDS │ │Redis │ │  ES  │ │SQS +   │
│  PG  │ │      │ │(opt) │ │Lambda  │
└──────┘ └──────┘ └──────┘ └────────┘
Multi-AZ   cache    search   async LLM
ACID       rate-    at       summaries
           limit    scale
              │
           ┌──┴──┐
           │ S3  │  ← docs >1MB, audit log archive (Glacier after 90d)
           └─────┘
```

**Key trade-offs:**
- **Start with Postgres tsvector, add Elasticsearch when >100K docs** — avoids ops complexity (3-node cluster, shard mgmt) until search quality or scale demands it
- **Docs >1MB in S3, small docs inline in Postgres** — adds ~50ms read latency but prevents row bloat that kills vacuum performance
- **Async LLM via SQS** — removes 2-10s LLM call from API response path (now <200ms), but summaries arrive later via poll/websocket

## CI/CD & Deployment

```
Push → GitHub Actions
         ├─ Lint (ruff) + Type check (mypy)
         ├─ Unit tests (no DB, fast)
         ├─ Integration tests (test DB)
         ├─ Build → Push to ECR
         └─ Deploy: Staging → Smoke tests → Canary 5% (10 min) → Full rollout
```

- **Blue/green** via ECS service updates — zero downtime, rollback in <30s by repointing to previous task definition
- **DB migrations** via Alembic, backwards-compatible only — column drops in N+1 deploy after code stops referencing them

## Security & Compliance

| Area | Approach |
|------|----------|
| **Auth** | OAuth2/OIDC via Auth0. JWT validated at ALB + API layer. Scoped tokens: `documents:read`, `documents:write`, `documents:admin` |
| **Encryption** | TLS 1.3 in transit. AES-256 at rest (RDS, S3, ES). Customer-managed KMS keys for document content |
| **Audit** | Append-only `change_history` — no UPDATEs or DELETEs. Every change has user ID, timestamp. Archive to S3 Glacier after 90 days |
| **GDPR** | Deletion cascades to all related data. Right-to-erasure endpoint. Pseudonymize user data after retention period |

**Trade-off:** Auth0 adds vendor dependency but saves months vs self-hosted auth. Append-only audit grows storage linearly — Glacier lifecycle keeps cost at ~$0.004/GB/month.

## Scalability & Resilience

- **Horizontal scaling:** ECS auto-scales on CPU (target 60%) + request count. API is stateless — no sticky sessions
- **Database:** RDS Multi-AZ (~30s auto-failover). Read replicas for GET endpoints. PgBouncer for connection pooling
- **Bulk operations:** 100+ changes processed as background SQS jobs — client gets job ID, polls for completion
- **Circuit breakers:** LLM fails open → deterministic summaries. ES fails → Postgres tsvector fallback (degraded, not down)

| Failure | Recovery |
|---------|----------|
| Postgres primary down | Multi-AZ failover ~30s, read replicas serve GETs |
| Elasticsearch down | Automatic fallback to Postgres full-text search |
| LLM API down | Deterministic summaries (already built in prototype) |
| Redis down | Direct DB queries, no data loss |

## Monitoring & Observability

```
Structured JSON logs  →  CloudWatch  →  OpenSearch Dashboards
Metrics (OpenTelemetry)  →  Datadog  →  PagerDuty alerts
Traces (OpenTelemetry)  →  AWS X-Ray
```

| Alert | Threshold | Why |
|-------|-----------|-----|
| API p99 latency | > 500ms | User experience |
| 5xx error rate | > 1% | Reliability |
| Version conflict rate | > 20% of PATCHes | High contention — may need real-time collab features |
| LLM failure rate | > 10% | AI features degraded |
| Search index lag | > 5 min | Stale search results |
| DB connection pool | > 80% utilization | Scale PgBouncer or add replicas |