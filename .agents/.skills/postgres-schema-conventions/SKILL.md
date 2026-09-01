---
name: postgres-schema-conventions
description: Use when creating or modifying database migrations, schema, or Postgres queries for the revenue recovery agent. Encodes the project's schema conventions and hand-written-first philosophy for backend/DB code.
---

# Postgres Schema & Migration Conventions

## Ownership
The developer wants to review and understand every migration and schema change personally — treat this as a collaborative draft, not an autonomous change. After generating a migration, summarize in plain language what it does and why, so it can be reviewed line by line before being applied.

## Schema conventions for this project
- Every domain table (cases, diagnoses, interventions, replies, state_transitions, outcomes) has a case_id foreign key back to cases, even where technically redundant, to make audit queries by case trivial
- audit_events is append-only: never update or delete rows in this table from application code
- All timestamps are stored in UTC with timezone awareness (timestamptz), never naive timestamps
- Use explicit migration files (numbered/timestamped), never rely on auto-generated schema sync in a way that bypasses a reviewable migration file
- Prefer explicit foreign key constraints and NOT NULL where the domain requires it, over permissive nullable columns "just in case"

## Idempotency requirement
Any migration or seed script must be safely re-runnable without duplicating data. Use ON CONFLICT DO NOTHING or explicit existence checks rather than assuming a clean slate.

## When writing queries
- Parameterize all queries; never string-format user or webhook-derived data into SQL
- For anything touching money amounts, use a fixed-precision numeric type (e.g. numeric(12,2)), never float