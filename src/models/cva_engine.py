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

class CreditValuationAdjustmentEngine:
    """
    Credit Valuation Adjustment (CVA) Pricing Engine:
    - Calculates CVA charges on OTC derivative portfolios under IFRS 13 & Basel III
    - Derives marginal default probabilities from annual hazard rates
    - Discounts expected exposure trajectories using risk-free yield curve
    - Updates CVA charges in PostgreSQL
    """

    def __init__(self, risk_free_rate=0.035, time_horizons=[0.25, 0.5, 1.0, 2.0, 3.0, 5.0]):
        self.engine = get_db_engine()
        self.risk_free_rate = risk_free_rate
        self.horizons = time_horizons

    def fetch_counterparty_profiles(self):
        """Queries Expected Exposure profiles for LATEST calculation date."""
        query = """
            SELECT 
                p.cva_id,
                c.counterparty_id,
                c.counterparty_code,
                c.counterparty_name,
                c.credit_rating,
                c.hazard_rate_annual,
                c.recovery_rate,
                p.expected_exposure_eur,
                p.pfe_95_eur,
                p.calc_date
            FROM fact_cva_pfe_results p
            JOIN dim_counterparties c ON p.counterparty_id = c.counterparty_id
            WHERE p.calc_date = (SELECT MAX(calc_date) FROM fact_cva_pfe_results);
        """
        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn)
        print(f"✅ Loaded {len(df)} counterparty exposure profiles for CVA pricing.")
        return df

    def calculate_cva_charges(self):
        """Computes CVA monetary charges (EUR) per counterparty."""
        df_cp = self.fetch_counterparty_profiles()
        results = []
        latest_date = datetime.now().strftime('%Y-%m-%d')

        print(f"\n💶 Executing CVA Pricing Engine (EUR Risk-Free Rate: {self.risk_free_rate*100:.1f}%)...")

        for _, row in df_cp.iterrows():
            cp_id = row['counterparty_id']
            cp_code = row['counterparty_code']
            cp_name = row['counterparty_name']
            hazard_rate = row['hazard_rate_annual']
            recovery_rate = row['recovery_rate']
            avg_ee = row['expected_exposure_eur']
            pfe_95 = row['pfe_95_eur']

            lgd = 1.0 - recovery_rate  # Loss Given Default

            # Compute CVA across time steps t_i
            cva_charge_eur = 0.0
            t_prev = 0.0

            for t in self.horizons:
                # 1. Marginal Default Probability dPD between t_prev and t
                survival_prev = np.exp(-hazard_rate * t_prev)
                survival_curr = np.exp(-hazard_rate * t)
                marginal_pd = survival_prev - survival_curr

                # 2. Risk-free Discount Factor D(t)
                discount_factor = np.exp(-self.risk_free_rate * t)

                # 3. Incremental CVA = LGD * EE(t) * dPD(t) * D(t)
                cva_step = lgd * avg_ee * marginal_pd * discount_factor
                cva_charge_eur += cva_step

                t_prev = t

            cva_charge_eur = round(cva_charge_eur, 2)

            results.append({
                "counterparty_id": int(cp_id),
                "calc_date": latest_date,
                "cva_charge_eur": cva_charge_eur
            })

            print(f"💰 {cp_code:12s} ({cp_name:28s}) | Rating: {row['credit_rating']:3s} | CVA Charge: EUR {cva_charge_eur:10,.2f}")

        # Save CVA Charges to PostgreSQL
        self._save_to_postgresql(results)

    def _save_to_postgresql(self, results):
        """Updates CVA charges directly in fact_cva_pfe_results table."""
        if not results:
            return

        print(f"\n📥 Updating CVA pricing charges in PostgreSQL...")
        
        with self.engine.begin() as conn:
            for res in results:
                # FIXED: Uses CAST(:cdate AS DATE) instead of :cdate::DATE
                update_query = text("""
                    UPDATE fact_cva_pfe_results
                    SET cva_charge_eur = :cva
                    WHERE counterparty_id = :cp_id AND calc_date = CAST(:cdate AS DATE);
                """)
                conn.execute(update_query, {
                    "cva": float(res["cva_charge_eur"]),
                    "cp_id": int(res["counterparty_id"]),
                    "cdate": str(res["calc_date"])
                })

        print("🎉 CVA Pricing charges committed to PostgreSQL successfully!")

if __name__ == "__main__":
    cva_engine = CreditValuationAdjustmentEngine(risk_free_rate=0.035)
    cva_engine.calculate_cva_charges()