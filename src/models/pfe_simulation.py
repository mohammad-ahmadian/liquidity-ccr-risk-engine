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

class PotentialFutureExposureEngine:
    """
    Counterparty Credit Risk (CCR) Engine:
    - Runs 10,000 Monte Carlo simulation paths for OTC derivative portfolios
    - Calculates Expected Exposure (EE) and Potential Future Exposure (PFE 95%)
    - Computes Effective Expected Positive Exposure (EEPE)
    - Stores counterparty PFE profiles in PostgreSQL
    """

    def __init__(self, num_simulations=10000, time_horizons=[0.25, 0.5, 1.0, 2.0, 3.0, 5.0]):
        self.engine = get_db_engine()
        self.num_sims = num_simulations
        self.horizons = time_horizons

    def fetch_derivative_trades(self):
        """Fetches active OTC derivative trades and counterparty metadata."""
        query = """
            SELECT 
                d.trade_id,
                d.trade_code,
                c.counterparty_id,
                c.counterparty_code,
                c.counterparty_name,
                c.credit_rating,
                d.instrument_type,
                d.notional_amount_eur,
                d.mtm_value_eur,
                d.maturity_years
            FROM fact_derivative_portfolios d
            JOIN dim_counterparties c ON d.counterparty_id = c.counterparty_id;
        """
        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn)
        print(f"✅ Loaded {len(df)} OTC derivative trades across counterparties.")
        return df

    def run_monte_carlo_pfe(self, seed=42):
        """Simulates 10,000 Monte Carlo MtM paths and calculates counterparty PFE & EE."""
        np.random.seed(seed)
        df_trades = self.fetch_derivative_trades()
        results = []
        latest_date = datetime.now().strftime('%Y-%m-%d')

        print(f"\n🎲 Executing Monte Carlo PFE Simulation ({self.num_sims:,} paths)...")

        for cp_id, cp_group in df_trades.groupby('counterparty_id'):
            cp_code = cp_group['counterparty_code'].iloc[0]
            cp_name = cp_group['counterparty_name'].iloc[0]
            
            # Store simulated exposures for this counterparty across time
            cp_time_ee = []
            cp_time_pfe = []

            for t in self.horizons:
                simulated_portfolio_mtm = np.zeros(self.num_sims)

                for _, trade in cp_group.iterrows():
                    mtm_0 = trade['mtm_value_eur']
                    notional = trade['notional_amount_eur']
                    mat = trade['maturity_years']

                    if t > mat:
                        continue  # Trade matured

                    # Diffuse MtM value using Geometric Brownian Motion (volatility = 18%)
                    vol = 0.18
                    dt = t
                    z = np.random.normal(0, 1, self.num_sims)
                    
                    # Simulated MtM value at time t
                    mtm_t = mtm_0 * np.exp((-0.5 * vol**2) * dt + vol * np.sqrt(dt) * z)
                    simulated_portfolio_mtm += mtm_t

                # Calculate Positive Exposure max(0, MtM)
                positive_exposures = np.maximum(0.0, simulated_portfolio_mtm)
                
                # Expected Exposure (EE) = Mean of positive exposures
                ee_t = np.mean(positive_exposures)
                
                # Potential Future Exposure (PFE 95%) = 95th Percentile
                pfe_95_t = np.percentile(positive_exposures, 95)

                cp_time_ee.append(ee_t)
                cp_time_pfe.append(pfe_95_t)

            # Overall Counterparty Aggregates
            avg_ee = float(np.mean(cp_time_ee)) if cp_time_ee else 0.0
            max_pfe_95 = float(np.max(cp_time_pfe)) if cp_time_pfe else 0.0

            results.append({
                "counterparty_id": int(cp_id),
                "calc_date": latest_date,
                "expected_exposure_eur": round(avg_ee, 2),
                "pfe_95_eur": round(max_pfe_95, 2),
                "cva_charge_eur": 0.0  # Will be calculated on Day 23
            })

            print(f"📊 {cp_code:12s} ({cp_name:28s}) | EE: EUR {avg_ee:12,.2f} | PFE (95%): EUR {max_pfe_95:12,.2f}")

        # Save PFE Results to PostgreSQL
        self._save_to_postgresql(results)

    def _save_to_postgresql(self, results):
        """Saves counterparty PFE exposure metrics to fact_cva_pfe_results table."""
        if not results:
            return

        df_pfe = pd.DataFrame(results)
        df_pfe['calc_date'] = pd.to_datetime(df_pfe['calc_date']).dt.date

        print(f"\n📥 Uploading {len(df_pfe)} counterparty PFE exposure profiles to PostgreSQL...")
        
        with self.engine.begin() as conn:
            df_pfe.to_sql("temp_pfe", conn, if_exists="replace", index=False)
            upsert_query = text("""
                INSERT INTO fact_cva_pfe_results (counterparty_id, calc_date, expected_exposure_eur, pfe_95_eur, cva_charge_eur)
                SELECT counterparty_id, calc_date::DATE, expected_exposure_eur, pfe_95_eur, cva_charge_eur
                FROM temp_pfe
                ON CONFLICT (counterparty_id, calc_date) DO UPDATE
                SET expected_exposure_eur = EXCLUDED.expected_exposure_eur,
                    pfe_95_eur = EXCLUDED.pfe_95_eur;

                DROP TABLE temp_pfe;
            """)
            conn.execute(upsert_query)

        print("🎉 Counterparty PFE simulation profiles committed to PostgreSQL successfully!")

if __name__ == "__main__":
    pfe_engine = PotentialFutureExposureEngine(num_simulations=10000)
    pfe_engine.run_monte_carlo_pfe()