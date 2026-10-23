-- ============================================================================
-- ZionhiltPay Database Schema (PostgreSQL 15+)
-- Double-entry ledger fintech wallet system with rewards + device insurance
-- Powered by Zionhilt
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "citext";

-- ----------------------------------------------------------------------------
-- ENUM TYPES
-- ----------------------------------------------------------------------------
CREATE TYPE user_role AS ENUM ('user', 'admin', 'super_admin');
CREATE TYPE otp_channel AS ENUM ('email', 'sms');
CREATE TYPE otp_purpose AS ENUM ('registration', 'login', 'pin_reset', 'password_reset', 'transaction');
CREATE TYPE account_type AS ENUM (
    'user_wallet',          -- individual user spendable balance
    'user_reward',          -- individual user reward/cashback balance
    'user_insurance',       -- individual user device-insurance pool balance
    'platform_revenue',     -- platform commission/revenue clearing account
    'platform_reward_pool', -- funding source for rewards (contra account)
    'platform_insurance_pool', -- funding source for insurance (contra account)
    'external_gateway',     -- represents external bank/payment gateway (contra account)
    'platform_loan_pool'    -- lending capital (negative balance = money currently lent out)
);
CREATE TYPE transaction_type AS ENUM (
    'deposit', 'withdrawal', 'transfer', 'reward_credit', 'insurance_contribution',
    'insurance_claim_payout', 'fee', 'reversal', 'loan_disbursement', 'loan_repayment'
);
CREATE TYPE transaction_status AS ENUM ('pending', 'processing', 'completed', 'failed', 'reversed', 'flagged');
CREATE TYPE device_type AS ENUM ('phone', 'laptop', 'tablet', 'other');
CREATE TYPE device_status AS ENUM ('active', 'lost', 'stolen', 'damaged', 'claim_paid', 'inactive');
CREATE TYPE fraud_severity AS ENUM ('low', 'medium', 'high', 'critical');

-- ----------------------------------------------------------------------------
-- USERS
-- ----------------------------------------------------------------------------
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    full_name VARCHAR(150) NOT NULL,
    email CITEXT UNIQUE NOT NULL,
    phone_number VARCHAR(20) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role user_role NOT NULL DEFAULT 'user',

    -- verification state
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    phone_verified BOOLEAN NOT NULL DEFAULT FALSE,
    preferred_otp_channel otp_channel NOT NULL DEFAULT 'email',

    -- transaction PIN (separate from login password)
    pin_hash VARCHAR(255),
    pin_set BOOLEAN NOT NULL DEFAULT FALSE,
    pin_failed_attempts SMALLINT NOT NULL DEFAULT 0,
    pin_locked_until TIMESTAMPTZ,

    -- account state
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_frozen BOOLEAN NOT NULL DEFAULT FALSE,
    freeze_reason TEXT,

    -- identity: username, account number, government ID (encrypted) and KYC review state
    username VARCHAR(20),
    account_number VARCHAR(10),
    id_type VARCHAR(20),
    id_number_enc TEXT,          -- Fernet ciphertext, never exposed by the API
    id_number_hash VARCHAR(64),  -- keyed HMAC for one-ID-one-account
    id_number_last4 VARCHAR(4),
    id_submitted_at TIMESTAMPTZ,
    kyc_status VARCHAR(20) NOT NULL DEFAULT 'not_submitted',
    kyc_reviewed_by UUID,
    kyc_reviewed_at TIMESTAMPTZ,
    kyc_note TEXT,
    account_tier SMALLINT NOT NULL DEFAULT 1,   -- 1, 2 or 3: sets transaction and balance limits
    profile_photo VARCHAR(64),                  -- file name only (files live outside the database)

    kyc_level SMALLINT NOT NULL DEFAULT 0, -- 0=unverified,1=basic,2=full
    tier_daily_limit NUMERIC(18,2) NOT NULL DEFAULT 50000.00,

    last_login_at TIMESTAMPTZ,
    last_login_ip VARCHAR(64),

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_phone ON users(phone_number);
CREATE UNIQUE INDEX uq_users_username ON users (username);
CREATE UNIQUE INDEX uq_users_account_number ON users (account_number);
CREATE UNIQUE INDEX uq_users_id_hash ON users (id_type, id_number_hash);

-- (citext extension already created at top of file)

-- ----------------------------------------------------------------------------
-- OTP CODES
-- ----------------------------------------------------------------------------
CREATE TABLE otp_codes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    -- allow OTP before user record fully exists (pre-registration verification)
    target_email CITEXT,
    target_phone VARCHAR(20),
    channel otp_channel NOT NULL,
    purpose otp_purpose NOT NULL,
    code_hash VARCHAR(255) NOT NULL,
    attempts SMALLINT NOT NULL DEFAULT 0,
    max_attempts SMALLINT NOT NULL DEFAULT 5,
    consumed BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_otp_user ON otp_codes(user_id);
CREATE INDEX idx_otp_lookup ON otp_codes(target_email, target_phone, purpose, consumed);

-- ----------------------------------------------------------------------------
-- ACCOUNTS (ledger accounts — every wallet/pool is a ledger account)
-- ----------------------------------------------------------------------------
CREATE TABLE accounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE, -- NULL for platform-level accounts
    account_type account_type NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'NGN',
    -- cached balance, always must equal SUM(ledger_entries) for this account.
    -- Reconciled by services/ledger.py on every write inside the same transaction.
    balance NUMERIC(18,2) NOT NULL DEFAULT 0.00,
    is_platform_account BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, account_type, currency)
);

CREATE INDEX idx_accounts_user ON accounts(user_id);
CREATE INDEX idx_accounts_type ON accounts(account_type);

-- ----------------------------------------------------------------------------
-- TRANSACTIONS (business-level event; 1 transaction -> N balanced ledger_entries)
-- ----------------------------------------------------------------------------
CREATE TABLE transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    reference VARCHAR(40) UNIQUE NOT NULL, -- e.g. ZHP-20260818-XXXXXXXX
    initiator_user_id UUID REFERENCES users(id),
    counterparty_user_id UUID REFERENCES users(id), -- for transfers
    type transaction_type NOT NULL,
    status transaction_status NOT NULL DEFAULT 'pending',

    amount NUMERIC(18,2) NOT NULL CHECK (amount > 0),
    fee_amount NUMERIC(18,2) NOT NULL DEFAULT 0.00,
    reward_amount NUMERIC(18,2) NOT NULL DEFAULT 0.00,
    insurance_contribution NUMERIC(18,2) NOT NULL DEFAULT 0.00,
    currency VARCHAR(3) NOT NULL DEFAULT 'NGN',

    narration TEXT,
    gateway_reference VARCHAR(100), -- mock payment gateway ref for deposits/withdrawals
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    ip_address VARCHAR(64),
    device_fingerprint VARCHAR(255),

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_txn_initiator ON transactions(initiator_user_id);
CREATE INDEX idx_txn_counterparty ON transactions(counterparty_user_id);
CREATE INDEX idx_txn_status ON transactions(status);
CREATE INDEX idx_txn_created ON transactions(created_at DESC);
CREATE INDEX idx_txn_reference ON transactions(reference);

-- ----------------------------------------------------------------------------
-- LEDGER ENTRIES (immutable double-entry rows; debits/credits must balance
-- to zero per transaction_id — enforced in application layer + trigger check)
-- ----------------------------------------------------------------------------
CREATE TABLE ledger_entries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    transaction_id UUID NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES accounts(id),
    direction CHAR(1) NOT NULL CHECK (direction IN ('D','C')), -- Debit / Credit
    amount NUMERIC(18,2) NOT NULL CHECK (amount > 0),
    balance_after NUMERIC(18,2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_ledger_txn ON ledger_entries(transaction_id);
CREATE INDEX idx_ledger_account ON ledger_entries(account_id);

-- Ledger entries are append-only. Prevent UPDATE/DELETE at the DB level.
CREATE RULE ledger_entries_no_update AS ON UPDATE TO ledger_entries DO INSTEAD NOTHING;
CREATE RULE ledger_entries_no_delete AS ON DELETE TO ledger_entries DO INSTEAD NOTHING;

-- ----------------------------------------------------------------------------
-- DEVICES (insurance-eligible devices; MAC-address tracking is v1.1 —
-- schema includes the column now so v1.1 doesn't require a migration)
-- ----------------------------------------------------------------------------
CREATE TABLE devices (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_type device_type NOT NULL,
    brand VARCHAR(80),
    model VARCHAR(80),
    serial_number VARCHAR(120),
    mac_address VARCHAR(17), -- format AA:BB:CC:DD:EE:FF — populated/used from v1.1
    estimated_value NUMERIC(18,2) NOT NULL,
    insured_value NUMERIC(18,2) NOT NULL DEFAULT 0.00, -- coverage accrued so far
    status device_status NOT NULL DEFAULT 'active',
    registered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ, -- reserved for v1.1 tracking pings
    last_seen_location JSONB, -- reserved for v1.1 {lat, lng, source}
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_devices_user ON devices(user_id);
CREATE INDEX idx_devices_mac ON devices(mac_address);

-- ----------------------------------------------------------------------------
-- INSURANCE CLAIMS
-- ----------------------------------------------------------------------------
CREATE TABLE insurance_claims (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    device_id UUID NOT NULL REFERENCES devices(id),
    user_id UUID NOT NULL REFERENCES users(id),
    claim_type VARCHAR(20) NOT NULL, -- 'lost','stolen','damaged'
    description TEXT,
    requested_amount NUMERIC(18,2) NOT NULL,
    approved_amount NUMERIC(18,2),
    status VARCHAR(20) NOT NULL DEFAULT 'submitted', -- submitted, under_review, approved, rejected, paid
    reviewed_by UUID REFERENCES users(id),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_claims_user ON insurance_claims(user_id);
CREATE INDEX idx_claims_device ON insurance_claims(device_id);

-- ----------------------------------------------------------------------------
-- FRAUD FLAGS
-- ----------------------------------------------------------------------------
CREATE TABLE fraud_flags (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    transaction_id UUID REFERENCES transactions(id),
    rule_code VARCHAR(60) NOT NULL, -- e.g. VELOCITY_LIMIT, LARGE_AMOUNT, NEW_DEVICE_HIGH_VALUE
    severity fraud_severity NOT NULL DEFAULT 'low',
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_by UUID REFERENCES users(id),
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_fraud_user ON fraud_flags(user_id);
CREATE INDEX idx_fraud_txn ON fraud_flags(transaction_id);
CREATE INDEX idx_fraud_resolved ON fraud_flags(resolved);

-- ----------------------------------------------------------------------------
-- AUDIT LOGS (append-only trail for every sensitive action)
-- ----------------------------------------------------------------------------
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    actor_user_id UUID REFERENCES users(id),
    actor_role user_role,
    action VARCHAR(80) NOT NULL, -- e.g. LOGIN_SUCCESS, PIN_CHANGE, TRANSFER_CREATED, ADMIN_FREEZE_ACCOUNT
    entity_type VARCHAR(60),
    entity_id UUID,
    ip_address VARCHAR(64),
    user_agent TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_actor ON audit_logs(actor_user_id);
CREATE INDEX idx_audit_action ON audit_logs(action);
CREATE INDEX idx_audit_created ON audit_logs(created_at DESC);

CREATE RULE audit_logs_no_update AS ON UPDATE TO audit_logs DO INSTEAD NOTHING;
CREATE RULE audit_logs_no_delete AS ON DELETE TO audit_logs DO INSTEAD NOTHING;

-- ----------------------------------------------------------------------------
-- REFRESH TOKENS (for JWT refresh rotation / revocation)
-- ----------------------------------------------------------------------------
CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    replaced_by UUID REFERENCES refresh_tokens(id),
    ip_address VARCHAR(64),
    user_agent TEXT,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_refresh_user ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_hash ON refresh_tokens(token_hash);

-- ----------------------------------------------------------------------------
-- PLATFORM CONFIG (single-row settings table for reward %, insurance %, etc.)
-- ----------------------------------------------------------------------------
CREATE TABLE platform_config (
    id SMALLINT PRIMARY KEY DEFAULT 1,
    reward_rate NUMERIC(6,4) NOT NULL DEFAULT 0.0050,        -- 0.50% of txn value back as reward
    insurance_contribution_rate NUMERIC(6,4) NOT NULL DEFAULT 0.0100, -- 1% of commission -> insurance pool
    transaction_fee_rate NUMERIC(6,4) NOT NULL DEFAULT 0.0150, -- 1.5% platform commission on transfers
    withdrawal_fee_flat NUMERIC(18,2) NOT NULL DEFAULT 25.00,
    max_daily_transfer_default NUMERIC(18,2) NOT NULL DEFAULT 50000.00,
    fraud_velocity_window_minutes SMALLINT NOT NULL DEFAULT 10,
    fraud_velocity_max_txns SMALLINT NOT NULL DEFAULT 6,
    fraud_large_amount_threshold NUMERIC(18,2) NOT NULL DEFAULT 200000.00,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT single_row CHECK (id = 1)
);

INSERT INTO platform_config (id) VALUES (1) ON CONFLICT DO NOTHING;

-- ----------------------------------------------------------------------------
-- Trigger: keep updated_at fresh
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_accounts_updated_at BEFORE UPDATE ON accounts
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_devices_updated_at BEFORE UPDATE ON devices
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ----------------------------------------------------------------------------
-- Seed platform-level accounts (singletons, user_id IS NULL)
-- ----------------------------------------------------------------------------
INSERT INTO accounts (account_type, currency, is_platform_account)
VALUES
    ('platform_revenue', 'NGN', TRUE),
    ('platform_reward_pool', 'NGN', TRUE),
    ('platform_insurance_pool', 'NGN', TRUE),
    ('external_gateway', 'NGN', TRUE),
    ('platform_loan_pool', 'NGN', TRUE)
ON CONFLICT DO NOTHING;


-- ----------------------------------------------------------------------------
-- TIER UPGRADE REQUESTS (BVN is encrypted exactly like ID numbers)
-- ----------------------------------------------------------------------------
CREATE TABLE tier_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_tier SMALLINT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',     -- draft | pending | approved | rejected
    bvn_enc TEXT,
    bvn_hash VARCHAR(64),
    bvn_last4 VARCHAR(4),
    address TEXT,
    document_file VARCHAR(64),                       -- proof-of-address image; file name only
    reviewed_by UUID,
    reviewed_at TIMESTAMPTZ,
    review_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    submitted_at TIMESTAMPTZ,
    edit_count SMALLINT NOT NULL DEFAULT 0       -- edits made after submitting
);
CREATE INDEX ix_tier_requests_user_id ON tier_requests(user_id);
CREATE UNIQUE INDEX uq_tier_requests_one_pending ON tier_requests (user_id) WHERE status = 'pending';
CREATE UNIQUE INDEX uq_tier_requests_one_open ON tier_requests (user_id) WHERE status IN ('draft','pending');
CREATE UNIQUE INDEX uq_tier_requests_bvn ON tier_requests (bvn_hash) WHERE status IN ('pending','approved') AND bvn_hash IS NOT NULL;

-- ----------------------------------------------------------------------------
-- LOANS
-- ----------------------------------------------------------------------------
CREATE TABLE loans (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    reference VARCHAR(40) UNIQUE NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id),
    principal NUMERIC(18,2) NOT NULL,
    interest NUMERIC(18,2) NOT NULL,
    total_due NUMERIC(18,2) NOT NULL,
    principal_repaid NUMERIC(18,2) NOT NULL DEFAULT 0,
    interest_repaid NUMERIC(18,2) NOT NULL DEFAULT 0,
    tenor_days SMALLINT NOT NULL,
    interest_rate_30d NUMERIC(6,4) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',    -- active | repaid
    disbursed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    due_at TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ
);
CREATE INDEX ix_loans_user_id ON loans(user_id);
CREATE UNIQUE INDEX uq_loans_one_active ON loans (user_id) WHERE status = 'active';

-- Exactly one platform account per type, and payouts are safe to retry.
CREATE UNIQUE INDEX uq_platform_account_type ON accounts (account_type, currency) WHERE user_id IS NULL;
CREATE UNIQUE INDEX uq_txn_client_reference ON transactions (initiator_user_id, ((metadata ->> 'client_reference'))) WHERE (metadata ->> 'client_reference') IS NOT NULL;


-- ----------------------------------------------------------------------------
-- PARTNERS (the scrolling logo strip on the landing page; managed by admins)
-- ----------------------------------------------------------------------------
CREATE TABLE partners (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(80) NOT NULL,
    website VARCHAR(300),
    logo_file VARCHAR(64),                 -- file name only (the image lives in the uploads folder)
    sort_order SMALLINT NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_partners_order ON partners (sort_order, created_at);
