-- 1. Dimension Table: Counterparty Metadata & Credit Ratings
CREATE TABLE IF NOT EXISTS dim_counterparties (
    counterparty_id SERIAL PRIMARY KEY,
    counterparty_code VARCHAR(20) UNIQUE NOT NULL,
    counterparty_name VARCHAR(100) NOT NULL,
    sector VARCHAR(50) NOT NULL, -- e.g., 'Bank', 'Corporate', 'Sovereign'
    credit_rating VARCHAR(10) NOT NULL, -- e.g., 'AAA', 'A', 'BBB', 'BB'
    hazard_rate_annual NUMERIC(6, 4) NOT NULL, -- Annual Default Probability
    recovery_rate NUMERIC(4, 2) NOT NULL DEFAULT 0.40,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Fact Table: Contractual Treasury Cash Flows (Maturity Laddering)
CREATE TABLE IF NOT EXISTS fact_cash_flows (
    cashflow_id SERIAL PRIMARY KEY,
    flow_code VARCHAR(20) UNIQUE NOT NULL,
    flow_type VARCHAR(20) NOT NULL, -- 'Inflow' or 'Outflow'
    maturity_bucket VARCHAR(20) NOT NULL, -- '1D', '7D', '30D', '90D', '1Y', '1Y+'
    amount_eur NUMERIC(15, 2) NOT NULL,
    hqla_category VARCHAR(20) DEFAULT 'Non-HQLA', -- 'Level 1', 'Level 2A', 'Level 2B', 'Non-HQLA'
    asf_factor NUMERIC(4, 2) DEFAULT 0.00, -- Available Stable Funding factor (NSFR)
    rsf_factor NUMERIC(4, 2) DEFAULT 0.00, -- Required Stable Funding factor (NSFR)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Fact Table: OTC Derivative Trades (Counterparty Risk Exposure)
CREATE TABLE IF NOT EXISTS fact_derivative_portfolios (
    trade_id SERIAL PRIMARY KEY,
    trade_code VARCHAR(20) UNIQUE NOT NULL,
    counterparty_id INT REFERENCES dim_counterparties(counterparty_id) ON DELETE CASCADE,
    instrument_type VARCHAR(50) NOT NULL, -- 'Interest Rate Swap', 'FX Forward'
    notional_amount_eur NUMERIC(15, 2) NOT NULL,
    mtm_value_eur NUMERIC(15, 2) NOT NULL, -- Mark-to-Market current value
    maturity_years NUMERIC(4, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Fact Table: Basel III LCR & NSFR Regulatory Calculations
CREATE TABLE IF NOT EXISTS fact_lcr_nsfr_summary (
    liquidity_id SERIAL PRIMARY KEY,
    calc_date DATE NOT NULL,
    total_hqla_eur NUMERIC(15, 2) NOT NULL,
    net_outflows_30d_eur NUMERIC(15, 2) NOT NULL,
    lcr_ratio_pct NUMERIC(8, 4) NOT NULL,
    asf_total_eur NUMERIC(15, 2) NOT NULL,
    rsf_total_eur NUMERIC(15, 2) NOT NULL,
    nsfr_ratio_pct NUMERIC(8, 4) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_liquidity_date UNIQUE (calc_date)
);

-- 5. Fact Table: CVA & PFE Counterparty Exposure Results
CREATE TABLE IF NOT EXISTS fact_cva_pfe_results (
    cva_id SERIAL PRIMARY KEY,
    counterparty_id INT REFERENCES dim_counterparties(counterparty_id) ON DELETE CASCADE,
    calc_date DATE NOT NULL,
    expected_exposure_eur NUMERIC(15, 2) NOT NULL,
    pfe_95_eur NUMERIC(15, 2) NOT NULL,
    cva_charge_eur NUMERIC(15, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_cva_cp_date UNIQUE (counterparty_id, calc_date)
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_cf_maturity ON fact_cash_flows(maturity_bucket);
CREATE INDEX IF NOT EXISTS idx_deriv_cp ON fact_derivative_portfolios(counterparty_id);