"""
0001 — initial schema

Creates all seven domain tables. Every column, constraint, and index is written
as explicit SQL so the schema is reviewable without running the ORM.

Upgrade:  cases → diagnoses → interventions → replies →
          state_transitions → audit_events → outcomes
Downgrade: reverse order (children before parents to satisfy FK constraints)
"""
from __future__ import annotations

from alembic import op

# revision identifiers
revision: str = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. cases (root table — all other tables FK to this) ──────────────────
    op.execute("""
        CREATE TABLE cases (
            id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            razorpay_event_id   TEXT        UNIQUE,
            case_type           TEXT        NOT NULL
                                CHECK (case_type IN (
                                    'failed_subscription',
                                    'overdue_receivable'
                                )),
            status              TEXT        NOT NULL DEFAULT 'open'
                                CHECK (status IN (
                                    'open', 'in_progress', 'promise_pending', 
                                    'payment_method_required', 'recovered',
                                    'escalated', 'stopped', 'unresolved'
                                )),
            customer_ref        TEXT        NOT NULL,
            amount              NUMERIC(12,2) NOT NULL,
            currency            TEXT        NOT NULL DEFAULT 'INR',
            raw_failure_reason  TEXT,
            tenure              INTEGER,
            raw_payload         JSONB,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ix_cases_status ON cases(status)")

    # ── 2. diagnoses ─────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE diagnoses (
            id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            case_id             UUID        NOT NULL REFERENCES cases(id),
            model_tier          TEXT        NOT NULL CHECK (model_tier IN ('8b', '70b')),
            prompt_version      TEXT        NOT NULL,
            prompt_hash         TEXT        NOT NULL,
            cause               TEXT        NOT NULL,
            confidence          NUMERIC(4,3) NOT NULL,
            recommended_action  TEXT        NOT NULL,
            raw_llm_response    TEXT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ix_diagnoses_case_id ON diagnoses(case_id)")

    # ── 3. interventions ─────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE interventions (
            id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            case_id         UUID        NOT NULL REFERENCES cases(id),
            channel         TEXT        NOT NULL DEFAULT 'mock'
                            CHECK (channel IN ('mock', 'whatsapp')),
            message_sent    TEXT        NOT NULL,
            attempt_number  INTEGER     NOT NULL DEFAULT 1,
            sent_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ix_interventions_case_id ON interventions(case_id)")

    # ── 4. replies ───────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE replies (
            id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            case_id             UUID        NOT NULL REFERENCES cases(id),
            raw_reply           TEXT        NOT NULL,
            classified_state    TEXT
                                CHECK (classified_state IN (
                                    'promise_made',
                                    'needs_new_payment_method',
                                    'disputed',
                                    'no_response',
                                    'opt_out',
                                    'unresolved'
                                )),
            classified_at       TIMESTAMPTZ,
            received_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ix_replies_case_id ON replies(case_id)")

    # ── 5. state_transitions ─────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE state_transitions (
            id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            case_id         UUID        NOT NULL REFERENCES cases(id),
            from_state      TEXT        NOT NULL,
            to_state        TEXT        NOT NULL,
            reason          TEXT        NOT NULL,
            transitioned_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ix_state_transitions_case_id ON state_transitions(case_id)")

    # ── 6. audit_events (append-only — never UPDATE or DELETE rows here) ─────
    op.execute("""
        CREATE TABLE audit_events (
            id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            case_id     UUID        REFERENCES cases(id),
            event_type  TEXT        NOT NULL,
            payload     JSONB       NOT NULL DEFAULT '{}',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ix_audit_events_case_id_created ON audit_events(case_id, created_at)")

    # ── 7. outcomes ──────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE outcomes (
            id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            case_id          UUID        NOT NULL UNIQUE REFERENCES cases(id),
            final_state      TEXT        NOT NULL
                             CHECK (final_state IN (
                                 'recovered', 'pending',
                                 'escalated', 'stopped', 'unresolved'
                             )),
            amount_recovered NUMERIC(12,2) NOT NULL DEFAULT 0.00,
            resolved_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    # Drop in reverse dependency order (children before parents)
    op.execute("DROP TABLE IF EXISTS outcomes")
    op.execute("DROP TABLE IF EXISTS audit_events")
    op.execute("DROP TABLE IF EXISTS state_transitions")
    op.execute("DROP TABLE IF EXISTS replies")
    op.execute("DROP TABLE IF EXISTS interventions")
    op.execute("DROP TABLE IF EXISTS diagnoses")
    op.execute("DROP TABLE IF EXISTS cases")
