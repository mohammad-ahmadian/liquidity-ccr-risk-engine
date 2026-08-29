import sys
import os

# Point directly to the src/database directory
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.abspath(os.path.join(CURRENT_DIR, '../database'))
if DB_DIR not in sys.path:
    sys.path.insert(0, DB_DIR)

from db_connection import get_db_engine

import numpy as np
import pandas as pd
from datetime import datetime
from sqlalchemy import text

class RegulatoryLiquidityEngine:
    """
    Basel III Regulatory Liquidity Engine:
    - Calculates High-Quality Liquid Assets (HQLA) with Level 1 / 2A / 2B Haircuts
    - Calculates 30-Day Stressed Net Cash Outflows (with 75% inflow cap)
    - Computes Liquidity Coverage Ratio (LCR %) >= 100%
    - Computes Net Stable Funding Ratio (NSFR %) >= 100%
    - Stores summary metrics in PostgreSQL
    """

    def __init__(self):
        self.engine = get_db_engine()

    def fetch_cash_flows(self):
        """Fetches contractual cash flows and HQLA classifications from DB."""
        query = """
            SELECT 
                cashflow_id,
                flow_code,
                flow_type,
                maturity_bucket,
                amount_eur,
                hqla_category,
                asf_factor,
                rsf_factor
            FROM fact_cash_flows;
        """
        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn)
        print(f"✅ Loaded {len(df)} treasury cash flow records.")
        return df

    def calculate_lcr_and_nsfr(self):
        """Computes HQLA, 30-Day Net Outflows, LCR %, ASF, RSF, and NSFR %."""
        df = self.fetch_cash_flows()
        latest_date = datetime.now().strftime('%Y-%m-%d')

        print("\n💧 Calculating Basel III Regulatory Liquidity Metrics...")

        # -------------------------------------------------------------
        # 1. HQLA Stock (Immediate Liquid Asset Reserves)
        # Level 1 (0% haircut) + Level 2A (15% haircut)
        # -------------------------------------------------------------
        hqla_l1 = df[(df['hqla_category'] == 'Level 1') & (df['maturity_bucket'] == '1D')]['amount_eur'].sum() * 1.00
        hqla_l2a = df[(df['hqla_category'] == 'Level 2A') & (df['maturity_bucket'] == '30D')]['amount_eur'].sum() * 0.85
        
        # Real HQLA stock reserve buffer
        total_hqla = float(hqla_l1 * 0.40 + hqla_l2a * 0.40)

        # -------------------------------------------------------------
        # 2. 30-Day Net Cash Outflows (1D + 7D + 30D buckets)
        # -------------------------------------------------------------
        short_term_buckets = ['1D', '7D', '30D']
        
        outflows_30d = df[(df['flow_type'] == 'Outflow') & (df['maturity_bucket'].isin(short_term_buckets))]['amount_eur'].sum()
        inflows_30d = df[(df['flow_type'] == 'Inflow') & (df['maturity_bucket'].isin(short_term_buckets))]['amount_eur'].sum()

        # Inflow Cap: Inflows cannot reduce outflows by more than 75%
        capped_inflows = min(inflows_30d, 0.75 * outflows_30d)
        net_outflows_30d = float(outflows_30d - capped_inflows)

        # -------------------------------------------------------------
        # 3. Liquidity Coverage Ratio (LCR %)
        # -------------------------------------------------------------
        lcr_ratio_pct = float((total_hqla / net_outflows_30d) * 100.0) if net_outflows_30d > 0 else 100.0

        # -------------------------------------------------------------
        # 4. Net Stable Funding Ratio (NSFR %)
        # -------------------------------------------------------------
        asf_total = float((df['amount_eur'] * df['asf_factor']).sum())
        rsf_total = float((df['amount_eur'] * df['rsf_factor']).sum())

        nsfr_ratio_pct = float((asf_total / rsf_total) * 100.0) if rsf_total > 0 else 100.0

        print("=======================================================")
        print("📊 BASEL III REGULATORY LIQUIDITY COMPLIANCE REPORT")
        print("=======================================================")
        print(f"• Total Stock of HQLA:           EUR {total_hqla:15,.2f}")
        print(f"• 30-Day Net Cash Outflows:      EUR {net_outflows_30d:15,.2f}")
        print(f"• Liquidity Coverage Ratio (LCR):    {lcr_ratio_pct:14.2f}% (Target: >= 100%)")
        print(f"• Available Stable Funding (ASF): EUR {asf_total:15,.2f}")
        print(f"• Required Stable Funding (RSF):  EUR {rsf_total:15,.2f}")
        print(f"• Net Stable Funding Ratio (NSFR):  {nsfr_ratio_pct:14.2f}% (Target: >= 100%)")
        print("=======================================================\n")

        # Save to PostgreSQL
        self._save_to_postgresql({
            "calc_date": latest_date,
            "total_hqla_eur": round(total_hqla, 2),
            "net_outflows_30d_eur": round(net_outflows_30d, 2),
            "lcr_ratio_pct": round(lcr_ratio_pct, 4),
            "asf_total_eur": round(asf_total, 2),
            "rsf_total_eur": round(rsf_total, 2),
            "nsfr_ratio_pct": round(nsfr_ratio_pct, 4)
        })

    def _save_to_postgresql(self, results):
        """Saves LCR & NSFR summary to fact_lcr_nsfr_summary table."""
        df_liq = pd.DataFrame([results])
        df_liq['calc_date'] = pd.to_datetime(df_liq['calc_date']).dt.date

        print("📥 Uploading LCR & NSFR regulatory metrics to PostgreSQL...")
        
        with self.engine.begin() as conn:
            df_liq.to_sql("temp_liq", conn, if_exists="replace", index=False)
            upsert_query = text("""
                INSERT INTO fact_lcr_nsfr_summary (calc_date, total_hqla_eur, net_outflows_30d_eur, lcr_ratio_pct, asf_total_eur, rsf_total_eur, nsfr_ratio_pct)
                SELECT calc_date::DATE, total_hqla_eur, net_outflows_30d_eur, lcr_ratio_pct, asf_total_eur, rsf_total_eur, nsfr_ratio_pct
                FROM temp_liq
                ON CONFLICT (calc_date) DO UPDATE
                SET total_hqla_eur = EXCLUDED.total_hqla_eur,
                    net_outflows_30d_eur = EXCLUDED.net_outflows_30d_eur,
                    lcr_ratio_pct = EXCLUDED.lcr_ratio_pct,
                    asf_total_eur = EXCLUDED.asf_total_eur,
                    rsf_total_eur = EXCLUDED.rsf_total_eur,
                    nsfr_ratio_pct = EXCLUDED.nsfr_ratio_pct;

                DROP TABLE temp_liq;
            """)
            conn.execute(upsert_query)

        print("🎉 Regulatory Liquidity metrics committed to PostgreSQL successfully!")

if __name__ == "__main__":
    liq_engine = RegulatoryLiquidityEngine()
    liq_engine.calculate_lcr_and_nsfr()