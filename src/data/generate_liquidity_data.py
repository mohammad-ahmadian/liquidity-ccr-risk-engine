import sys
import os

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.abspath(os.path.join(CURRENT_DIR, '../database'))
if DB_DIR not in sys.path:
    sys.path.insert(0, DB_DIR)

from db_connection import get_db_engine

import numpy as np
import pandas as pd
from sqlalchemy import text

def create_tables_if_not_exist(engine):
    """Creates tables from schema_liquidity.sql if missing."""
    schema_path = os.path.join(os.path.dirname(__file__), '../database/schema_liquidity.sql')
    if os.path.exists(schema_path):
        with open(schema_path, 'r') as f:
            sql = f.read()
        with engine.begin() as conn:
            conn.execute(text(sql))

def generate_and_load_liquidity_data(seed=42):
    np.random.seed(seed)
    engine = get_db_engine()
    create_tables_if_not_exist(engine)

    print("🔄 Generating Treasury Cash Flows & Counterparty Derivative Portfolios...")

    # 1. Counterparties
    counterparties = [
        {"code": "CP_BANK_01", "name": "Deutsche Bank AG", "sector": "Bank", "rating": "A", "hazard": 0.0120, "rec": 0.40},
        {"code": "CP_BANK_02", "name": "BNP Paribas SA", "sector": "Bank", "rating": "AA", "hazard": 0.0080, "rec": 0.40},
        {"code": "CP_CORP_01", "name": "Siemens AG", "sector": "Corporate", "rating": "A", "hazard": 0.0150, "rec": 0.35},
        {"code": "CP_CORP_02", "name": "BASF SE", "sector": "Corporate", "rating": "BBB", "hazard": 0.0350, "rec": 0.30},
        {"code": "CP_SOV_01", "name": "Bundesrepublik Deutschland", "sector": "Sovereign", "rating": "AAA", "hazard": 0.0010, "rec": 0.50}
    ]
    df_cp = pd.DataFrame(counterparties)
    df_cp.rename(columns={"code": "counterparty_code", "name": "counterparty_name", "rating": "credit_rating", "hazard": "hazard_rate_annual", "rec": "recovery_rate"}, inplace=True)

    with engine.begin() as conn:
        df_cp.to_sql("temp_cp", conn, if_exists="replace", index=False)
        conn.execute(text("""
            INSERT INTO dim_counterparties (counterparty_code, counterparty_name, sector, credit_rating, hazard_rate_annual, recovery_rate)
            SELECT counterparty_code, counterparty_name, sector, credit_rating, hazard_rate_annual, recovery_rate
            FROM temp_cp
            ON CONFLICT (counterparty_code) DO NOTHING;
            DROP TABLE temp_cp;
        """))

    with engine.connect() as conn:
        cp_map = pd.read_sql("SELECT counterparty_id, counterparty_code FROM dim_counterparties", conn)

    # 2. Treasury Cash Flows (Maturity Ladder & HQLA)
    cash_flows = [
        {"code": "CF_001", "type": "Inflow", "bucket": "1D", "amount": 150000000.0, "hqla": "Level 1", "asf": 0.00, "rsf": 0.00},
        {"code": "CF_002", "type": "Inflow", "bucket": "7D", "amount": 80000000.0, "hqla": "Level 1", "asf": 0.00, "rsf": 0.00},
        {"code": "CF_003", "type": "Inflow", "bucket": "30D", "amount": 120000000.0, "hqla": "Level 2A", "asf": 0.50, "rsf": 0.00},
        {"code": "CF_004", "type": "Outflow", "bucket": "1D", "amount": 90000000.0, "hqla": "Non-HQLA", "asf": 0.00, "rsf": 0.00},
        {"code": "CF_005", "type": "Outflow", "bucket": "7D", "amount": 60000000.0, "hqla": "Non-HQLA", "asf": 0.00, "rsf": 0.00},
        {"code": "CF_006", "type": "Outflow", "bucket": "30D", "amount": 110000000.0, "hqla": "Non-HQLA", "asf": 0.00, "rsf": 0.50},
        {"code": "CF_007", "type": "Inflow", "bucket": "1Y+", "amount": 500000000.0, "hqla": "Level 1", "asf": 1.00, "rsf": 0.00},
        {"code": "CF_008", "type": "Outflow", "bucket": "1Y+", "amount": 420000000.0, "hqla": "Non-HQLA", "asf": 0.00, "rsf": 0.85}
    ]
    df_cf = pd.DataFrame(cash_flows)
    df_cf.rename(columns={"code": "flow_code", "type": "flow_type", "bucket": "maturity_bucket", "amount": "amount_eur", "hqla": "hqla_category", "asf": "asf_factor", "rsf": "rsf_factor"}, inplace=True)

    with engine.begin() as conn:
        df_cf.to_sql("temp_cf", conn, if_exists="replace", index=False)
        conn.execute(text("""
            INSERT INTO fact_cash_flows (flow_code, flow_type, maturity_bucket, amount_eur, hqla_category, asf_factor, rsf_factor)
            SELECT flow_code, flow_type, maturity_bucket, amount_eur, hqla_category, asf_factor, rsf_factor
            FROM temp_cf
            ON CONFLICT (flow_code) DO NOTHING;
            DROP TABLE temp_cf;
        """))

    # 3. OTC Derivative Portfolios (Interest Rate Swaps & FX Forwards)
    trades = []
    for i in range(1, 101):
        cp_id = int(np.random.choice(cp_map['counterparty_id'].values))
        inst = np.random.choice(["Interest Rate Swap", "FX Forward"], p=[0.60, 0.40])
        notional = float(np.round(np.random.uniform(5000000, 50000000), 2))
        mtm = float(np.round(np.random.uniform(-1000000, 2500000), 2))
        mat = float(np.round(np.random.uniform(0.5, 5.0), 2))
        trades.append({
            "trade_code": f"TRADE_{i:04d}",
            "counterparty_id": cp_id,
            "instrument_type": inst,
            "notional_amount_eur": notional,
            "mtm_value_eur": mtm,
            "maturity_years": mat
        })
    df_trades = pd.DataFrame(trades)

    with engine.begin() as conn:
        df_trades.to_sql("temp_trades", conn, if_exists="replace", index=False)
        conn.execute(text("""
            INSERT INTO fact_derivative_portfolios (trade_code, counterparty_id, instrument_type, notional_amount_eur, mtm_value_eur, maturity_years)
            SELECT trade_code, counterparty_id, instrument_type, notional_amount_eur, mtm_value_eur, maturity_years
            FROM temp_trades
            ON CONFLICT (trade_code) DO NOTHING;
            DROP TABLE temp_trades;
        """))

    print("🎉 Liquidity Cash Flows & OTC Derivative Portfolios populated in PostgreSQL successfully!")

if __name__ == "__main__":
    generate_and_load_liquidity_data()