-- AM-Optimizer v2 Database Schema
-- Units: volume [mm³], support [cm³], time [min], XY surface [mm²]

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(100) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name       VARCHAR(255),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Customers table (only customer_number stored - no personal data)
CREATE TABLE IF NOT EXISTS customers (
    customer_number VARCHAR(100) PRIMARY KEY,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Inquiries table (one inquiry = one header row)
CREATE TABLE IF NOT EXISTS inquiries (
    inquiry_id      SERIAL PRIMARY KEY,
    inquiry_number  VARCHAR(100) NOT NULL,
    order_number    VARCHAR(100),
    customer_number VARCHAR(100) NOT NULL REFERENCES customers(customer_number),
    inquiry_date    DATE DEFAULT CURRENT_DATE,
    order_date      DATE,                          -- Auftragsdatum (only if confirmed order)
    requested_delivery_date DATE,
    status          VARCHAR(50) DEFAULT 'Anfrage', -- 'Anfrage' or 'Auftrag'
    machine         VARCHAR(50) NOT NULL,          -- Xline, EOS, M2_alt, M2_neu
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- Parts table (multiple parts per inquiry)
CREATE TABLE IF NOT EXISTS parts (
    part_id                 SERIAL PRIMARY KEY,
    inquiry_id              INTEGER NOT NULL REFERENCES inquiries(inquiry_id) ON DELETE CASCADE,
    material                VARCHAR(50) NOT NULL,  -- AlSi10Mg, 1.4404, IN718, IN625

    part_name               VARCHAR(255) NOT NULL,
    quantity                INTEGER NOT NULL DEFAULT 1,

    -- Part parameters
    part_volume_mm3         NUMERIC(12, 2) NOT NULL,   -- [mm³]
    stock_cm3               NUMERIC(10, 4),             -- [cm³] optional
    support_volume_cm3      NUMERIC(10, 4) NOT NULL,    -- [cm³]
    part_height_mm          NUMERIC(8, 2) NOT NULL,     -- [mm]

    -- Time parameters [min]
    prep_time_min           NUMERIC(8, 2),
    post_handling_time_min  NUMERIC(8, 2),
    blasting_time_min       NUMERIC(8, 2),
    leak_testing_time_min   NUMERIC(8, 2),
    qc_time_min             NUMERIC(8, 2),

    -- XY surface for platform calculation [mm²]
    projected_xy_surface_mm2 NUMERIC(12, 2),

    -- Manually calculated values (from import)
    manual_part_price_eur   NUMERIC(10, 2),
    manual_build_time_h     NUMERIC(8, 2),

    created_at              TIMESTAMP DEFAULT NOW(),
    updated_at              TIMESTAMP DEFAULT NOW()
);

-- Combined calculations table
CREATE TABLE IF NOT EXISTS combined_calculations (
    calc_id             SERIAL PRIMARY KEY,
    calc_number         VARCHAR(100) UNIQUE NOT NULL,  -- auto-generated, editable
    calc_name           VARCHAR(255) NOT NULL,
    machine             VARCHAR(50) NOT NULL,
    material_group      VARCHAR(50) NOT NULL,          -- AlSi10Mg, 1.4404, IN718_IN625
    platform_surface_mm2 NUMERIC(12, 2) NOT NULL,
    start_date          DATE,
    end_date            DATE,                          -- manufacturing deadline
    status              VARCHAR(50) DEFAULT 'open',
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW()
);

-- Parts selected for a combined calculation
CREATE TABLE IF NOT EXISTS calc_parts (
    id                      SERIAL PRIMARY KEY,
    calc_id                 INTEGER NOT NULL REFERENCES combined_calculations(calc_id) ON DELETE CASCADE,
    part_id                 INTEGER NOT NULL REFERENCES parts(part_id),

    -- Overrides (editable within calculation)
    material_override       VARCHAR(50),
    quantity_override       INTEGER,

    -- Regression results
    calc_part_price_eur     NUMERIC(10, 2),
    calc_build_time_h       NUMERIC(8, 2),
    price_reduction_eur     NUMERIC(10, 2),
    price_reduction_percent NUMERIC(5, 2),

    UNIQUE(calc_id, part_id)
);

-- Email notifications
CREATE TABLE IF NOT EXISTS email_notifications (
    notification_id     SERIAL PRIMARY KEY,
    calc_id             INTEGER REFERENCES combined_calculations(calc_id),
    customer_number     VARCHAR(100) NOT NULL REFERENCES customers(customer_number),
    inquiry_number      VARCHAR(100) NOT NULL,
    order_number        VARCHAR(100),
    notification_type   VARCHAR(50) NOT NULL,
    email_subject       TEXT NOT NULL,
    email_body          TEXT NOT NULL,
    status              VARCHAR(50) DEFAULT 'draft',  -- draft, reviewed, sent_manually
    generated_at        TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_inquiries_customer    ON inquiries(customer_number);
CREATE INDEX IF NOT EXISTS idx_inquiries_number      ON inquiries(inquiry_number);
CREATE INDEX IF NOT EXISTS idx_inquiries_order       ON inquiries(order_number);
CREATE INDEX IF NOT EXISTS idx_inquiries_machine     ON inquiries(machine);
CREATE INDEX IF NOT EXISTS idx_parts_inquiry         ON parts(inquiry_id);
CREATE INDEX IF NOT EXISTS idx_parts_material        ON parts(material);
CREATE INDEX IF NOT EXISTS idx_calc_parts_calc       ON calc_parts(calc_id);
CREATE INDEX IF NOT EXISTS idx_calc_parts_part       ON calc_parts(part_id);
CREATE INDEX IF NOT EXISTS idx_notifications_calc    ON email_notifications(calc_id);
