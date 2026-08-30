import sys
import os

# Force Python to add the root project directory to its path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
import numpy as np
import pandas as pd
from sqlalchemy import text
from src.database.db_connection import get_db_engine

def test_database_connection():
    """Test 1: Verify PostgreSQL LiquidityRiskDB connection works."""
    engine = get_db_engine()
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1;")).scalar()
    assert result == 1, "Database connection test failed."

def test_lcr_compliance_ratio():
    """Test 2: Verify Liquidity Coverage Ratio (LCR %) meets or exceeds 100% regulatory minimum."""
    engine = get_db_engine()
    with engine.connect() as conn:
        lcr = conn.execute(text("SELECT lcr_ratio_pct FROM fact_lcr_nsfr_summary LIMIT 1;")).scalar()
    assert lcr >= 100.0, f"LCR ratio {lcr}% is below 100% regulatory requirement."

def test_nsfr_compliance_ratio():
    """Test 3: Verify Net Stable Funding Ratio (NSFR %) meets or exceeds 100% regulatory minimum."""
    engine = get_db_engine()
    with engine.connect() as conn:
        nsfr = conn.execute(text("SELECT nsfr_ratio_pct FROM fact_lcr_nsfr_summary LIMIT 1;")).scalar()
    assert nsfr >= 100.0, f"NSFR ratio {nsfr}% is below 100% regulatory requirement."

def test_cva_charges_non_negative():
    """Test 4: Verify CVA charges are non-negative values."""
    engine = get_db_engine()
    with engine.connect() as conn:
        cva_vals = pd.read_sql("SELECT cva_charge_eur FROM fact_cva_pfe_results;", conn)['cva_charge_eur']
    assert (cva_vals >= 0.0).all(), "CVA charges must be non-negative."

def test_evt_var_non_negative():
    """Test 5: Verify 99.9% EVT Liquidity VaR yields a positive tail outflow estimate."""
    engine = get_db_engine()
    with engine.connect() as conn:
        evt_var = conn.execute(text("SELECT evt_var_999_eur FROM evt_liquidity_tail_risk LIMIT 1;")).scalar()
    assert evt_var > 0.0, "EVT 99.9% Liquidity VaR must be positive."