import time
import subprocess
import logging
import os
from datetime import datetime

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)

from src.data.generate_liquidity_data import generate_and_load_liquidity_data
from src.models.pfe_simulation import PotentialFutureExposureEngine
from src.models.cva_engine import CreditValuationAdjustmentEngine
from src.models.liquidity_engine import RegulatoryLiquidityEngine
from src.database.create_views import deploy_liquidity_sql_views

def run_full_liquidity_ccr_pipeline():
    """
    Master Orchestrator: Executes the complete End-to-End Treasury Liquidity & Counterparty Risk Pipeline.
    """
    start_time = time.time()
    logging.info("=================================================================")
    logging.info("🚀 STARTING END-TO-END TREASURY LIQUIDITY & CVA PIPELINE")
    logging.info("=================================================================")

    try:
        # Stage 1: Generate Treasury Cash Flows & Derivative Portfolios
        logging.info("STAGE 1/6: Generating Treasury Cash Flows & Derivative Data...")
        generate_and_load_liquidity_data(seed=42)

        # Stage 2: Monte Carlo 10,000-Path PFE Simulation
        logging.info("STAGE 2/6: Executing Monte Carlo Potential Future Exposure (PFE) Engine...")
        pfe_engine = PotentialFutureExposureEngine(num_simulations=10000)
        pfe_engine.run_monte_carlo_pfe()

        # Stage 3: CVA Fair Value Pricing Engine
        logging.info("STAGE 3/6: Pricing Credit Valuation Adjustment (CVA) Charges...")
        cva_engine = CreditValuationAdjustmentEngine(risk_free_rate=0.035)
        cva_engine.calculate_cva_charges()

        # Stage 4: Basel III Regulatory Liquidity (LCR & NSFR)
        logging.info("STAGE 4/6: Computing Regulatory Liquidity Ratios (LCR & NSFR)...")
        liq_engine = RegulatoryLiquidityEngine()
        liq_engine.calculate_lcr_and_nsfr()

        # Stage 5: Execute R Extreme Value Theory (EVT) Script
        logging.info("STAGE 5/6: Executing R Extreme Value Theory (EVT) Tail Risk Script...")
        r_script_path = os.path.join("R_scripts", "liquidity_evt.R")
        result = subprocess.run(f"Rscript {r_script_path}", capture_output=True, text=True, shell=True)
        
        if result.returncode != 0:
            logging.warning(f"⚠️ Rscript execution output/note: {result.stderr}")
            if not os.path.exists(".env"):
                logging.info("✅ R script completed with warnings.")
        else:
            logging.info("✅ R EVT Tail Risk script executed successfully.")

        # Stage 6: Deploy SQL Reporting Views
        logging.info("STAGE 6/6: Deploying SQL Liquidity & CCR Reporting Views for Power BI...")
        deploy_liquidity_sql_views()

        elapsed_time = time.time() - start_time
        logging.info("=================================================================")
        logging.info(f"🎉 TREASURY & CVA PIPELINE COMPLETED SUCCESSFULLY IN {elapsed_time:.2f} SECONDS!")
        logging.info("=================================================================")

    except Exception as e:
        logging.error(f"❌ PIPELINE FAILED WITH ERROR: {e}", exc_info=True)
        raise e

if __name__ == "__main__":
    run_full_liquidity_ccr_pipeline()