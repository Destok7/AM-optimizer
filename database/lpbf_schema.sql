-- ============================================================
-- LPBF Optimization Platform - Railway PostgreSQL Schema
-- All customer, inquiry, and order numbers are VARCHAR
-- No personal customer data stored (privacy by design)
-- ============================================================

-- ============================================================
-- TABLE 1: customers
-- Stores only the customer number - no personal data
-- ============================================================
CREATE TABLE customers (
    customer_number     VARCHAR(100) PRIMARY KEY,
    created_at          TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- TABLE 2: inquiries
-- One row per part type per inquiry/order
-- ============================================================
CREATE TABLE inquiries (
    inquiry_id                  SERIAL PRIMARY KEY,
    customer_number             VARCHAR(100) NOT NULL REFERENCES customers(customer_number),

    -- Identifiers assigned manually by the user
    inquiry_number              VARCHAR(100) NOT NULL,
    order_number                VARCHAR(100),
    inquiry_name                VARCHAR(255) NOT NULL,

    inquiry_date                DATE NOT NULL DEFAULT CURRENT_DATE,
    status                      VARCHAR(50) DEFAULT 'pending',
    -- 'pending', 'quoted', 'accepted', 'declined', 'combined'

    -- Part parameters (Slide 1 data model)
    part_name                   VARCHAR(255) NOT NULL,
    quantity                    INTEGER NOT NULL,
    part_volume_cm3             NUMERIC(10, 4) NOT NULL,
    stock_percent               NUMERIC(5, 2),
    support_volume_percent      NUMERIC(5, 2) NOT NULL,
    part_height_mm              NUMERIC(8, 2) NOT NULL,

    -- Time parameters
    prep_time_h                 NUMERIC(6, 2),
    post_handling_time_h        NUMERIC(6, 2),
    blasting_time_h             NUMERIC(6, 2),
    leak_testing_time_h         NUMERIC(6, 2),
    qc_time_h                   NUMERIC(6, 2),

    -- XY surface for nesting algorithm (Slide 5)
    projected_xy_surface_cm2    NUMERIC(10, 4),

    -- Lead time
    requested_delivery_date     DATE,
    lead_time_flexible          BOOLEAN DEFAULT FALSE,

    -- Outputs filled by scikit-learn regression model
    estimated_part_price_eur    NUMERIC(10, 2),
    estimated_build_time_h      NUMERIC(8, 2),

    created_at                  TIMESTAMP DEFAULT NOW(),
    updated_at                  TIMESTAMP DEFAULT NOW(),

    UNIQUE (inquiry_number, part_name)
);

-- ============================================================
-- TABLE 3: build_jobs
-- Represents a single LPBF build run
-- ============================================================
CREATE TABLE build_jobs (
    job_id                      SERIAL PRIMARY KEY,
    job_name                    VARCHAR(255) NOT NULL,
    status                      VARCHAR(50) DEFAULT 'open',
    -- 'open', 'planned', 'in_production', 'completed'

    -- Build platform constraints
    platform_xy_surface_cm2     NUMERIC(10, 4) NOT NULL,
    used_xy_surface_cm2         NUMERIC(10, 4) DEFAULT 0,
    available_xy_surface_cm2    NUMERIC(10, 4),

    -- Aggregated outputs
    total_price_eur             NUMERIC(10, 2),
    total_build_time_h          NUMERIC(8, 2),

    planned_start_date          DATE,
    planned_end_date            DATE,

    created_at                  TIMESTAMP DEFAULT NOW(),
    updated_at                  TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- TABLE 4: build_job_inquiries
-- Junction table linking inquiries to build jobs
-- ============================================================
CREATE TABLE build_job_inquiries (
    id                          SERIAL PRIMARY KEY,
    job_id                      INTEGER NOT NULL REFERENCES build_jobs(job_id),
    inquiry_id                  INTEGER NOT NULL REFERENCES inquiries(inquiry_id),
    assigned_at                 TIMESTAMP DEFAULT NOW(),

    -- Price recalculated after combining
    combined_part_price_eur     NUMERIC(10, 2),
    price_reduction_eur         NUMERIC(10, 2),
    price_reduction_percent     NUMERIC(5, 2),

    UNIQUE (job_id, inquiry_id)
);

-- ============================================================
-- TABLE 5: nesting_log
-- Audit trail of every nesting decision
-- ============================================================
CREATE TABLE nesting_log (
    log_id                          SERIAL PRIMARY KEY,
    job_id                          INTEGER REFERENCES build_jobs(job_id),
    inquiry_id                      INTEGER REFERENCES inquiries(inquiry_id),

    decision                        VARCHAR(50) NOT NULL,
    -- 'nested', 'rejected_no_space', 'rejected_deadline', 'pending_customer_approval'

    available_surface_before_cm2    NUMERIC(10, 4),
    surface_used_cm2                NUMERIC(10, 4),
    available_surface_after_cm2     NUMERIC(10, 4),

    lead_time_impact_h              NUMERIC(8, 2),
    gpt_reasoning_summary           TEXT,
    -- GPT-4 reasoning for the nesting decision

    decided_at                      TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- TABLE 6: email_notifications
-- GPT-4 generated email drafts for manual sending
-- No email addresses stored - looked up externally by user
-- ============================================================
CREATE TABLE email_notifications (
    notification_id     SERIAL PRIMARY KEY,
    customer_number     VARCHAR(100) NOT NULL REFERENCES customers(customer_number),
    inquiry_number      VARCHAR(100) NOT NULL,
    order_number        VARCHAR(100),
    job_id              INTEGER REFERENCES build_jobs(job_id),

    notification_type   VARCHAR(50) NOT NULL,
    -- 'price_reduction_current', 'price_reduction_returning'

    email_subject       TEXT NOT NULL,
    email_body          TEXT NOT NULL,
    -- GPT-4 generated draft, ready for user to copy and send manually

    generated_at        TIMESTAMP DEFAULT NOW(),
    status              VARCHAR(50) DEFAULT 'draft'
    -- 'draft', 'reviewed', 'sent_manually'
);

-- ============================================================
-- INDEXES for query performance
-- ============================================================
CREATE INDEX idx_inquiries_customer        ON inquiries(customer_number);
CREATE INDEX idx_inquiries_status          ON inquiries(status);
CREATE INDEX idx_inquiries_inquiry_number  ON inquiries(inquiry_number);
CREATE INDEX idx_inquiries_order_number    ON inquiries(order_number);
CREATE INDEX idx_build_job_inquiries_job   ON build_job_inquiries(job_id);
CREATE INDEX idx_build_job_inquiries_inq   ON build_job_inquiries(inquiry_id);
CREATE INDEX idx_nesting_log_job           ON nesting_log(job_id);
CREATE INDEX idx_nesting_log_inquiry       ON nesting_log(inquiry_id);
CREATE INDEX idx_email_notifications_cust  ON email_notifications(customer_number);
