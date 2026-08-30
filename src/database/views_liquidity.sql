-- ====================================================================
-- SQL REPORTING VIEWS FOR TREASURY LIQUIDITY & CVA DASHBOARD
-- ====================================================================

-- View 1: Basel III Regulatory LCR & NSFR Summary
CREATE OR REPLACE VIEW vw_lcr_nsfr_regulatory_summary AS
SELECT 
    liquidity_id,
    calc_date,
    total_hqla_eur,
    net_outflows_30d_eur,
    lcr_ratio_pct,
    asf_total_eur,
    rsf_total_eur,
    nsfr_ratio_pct,
    CASE 
        WHEN lcr_ratio_pct >= 100.0 THEN 'Compliant (LCR >= 100%)'
        ELSE 'Non-Compliant (LCR < 100%)'
    END AS lcr_status,
    CASE 
        WHEN nsfr_ratio_pct >= 100.0 THEN 'Compliant (NSFR >= 100%)'
        ELSE 'Non-Compliant (NSFR < 100%)'
    END AS nsfr_status
FROM fact_lcr_nsfr_summary;

-- View 2: Contractual Cash Flow Maturity Laddering
CREATE OR REPLACE VIEW vw_cashflow_maturity_ladder AS
SELECT 
    cashflow_id,
    flow_code,
    flow_type,
    maturity_bucket,
    amount_eur,
    hqla_category,
    asf_factor,
    rsf_factor,
    CASE 
        WHEN maturity_bucket = '1D' THEN 1
        WHEN maturity_bucket = '7D' THEN 2
        WHEN maturity_bucket = '30D' THEN 3
        WHEN maturity_bucket = '90D' THEN 4
        WHEN maturity_bucket = '1Y' THEN 5
        ELSE 6
    END AS bucket_order
FROM fact_cash_flows
ORDER BY bucket_order ASC;

-- View 3: Counterparty Credit Risk, PFE & CVA Summary
CREATE OR REPLACE VIEW vw_counterparty_cva_pfe_summary AS
SELECT 
    p.cva_id,
    c.counterparty_id,
    c.counterparty_code,
    c.counterparty_name,
    c.sector,
    c.credit_rating,
    c.hazard_rate_annual,
    c.recovery_rate,
    p.calc_date,
    p.expected_exposure_eur,
    p.pfe_95_eur,
    p.cva_charge_eur,
    ROUND((p.cva_charge_eur / p.expected_exposure_eur * 100)::numeric, 4) AS cva_pct_of_ee
FROM fact_cva_pfe_results p
JOIN dim_counterparties c ON p.counterparty_id = c.counterparty_id;

-- View 4: OTC Derivative Trade Portfolio Detail
CREATE OR REPLACE VIEW vw_derivative_portfolio_detail AS
SELECT 
    d.trade_id,
    d.trade_code,
    c.counterparty_code,
    c.counterparty_name,
    c.credit_rating,
    d.instrument_type,
    d.notional_amount_eur,
    d.mtm_value_eur,
    d.maturity_years,
    CASE 
        WHEN d.mtm_value_eur > 0 THEN 'Positive (Bank Asset)'
        ELSE 'Negative (Bank Liability)'
    END AS mtm_sign
FROM fact_derivative_portfolios d
JOIN dim_counterparties c ON d.counterparty_id = c.counterparty_id;

-- View 5: R Extreme Value Theory (EVT) Liquidity Tail Risk Summary
CREATE OR REPLACE VIEW vw_evt_liquidity_tail_risk_summary AS
SELECT 
    evt_id,
    calc_date,
    threshold_u,
    gpd_shape_xi,
    gpd_scale_beta,
    evt_var_999_eur,
    evt_es_999_eur
FROM evt_liquidity_tail_risk;