# ====================================================================
# EXTREME VALUE THEORY (EVT) LIQUIDITY TAIL RISK ENGINE (R)
# ====================================================================

# Set exact project working directory
setwd("D:/Mohammad/Uni Courses/Summer 2025/2026/SQL/2026 Plan/Githubcodes/liquidity-ccr-risk-engine")

# Read real environment variables from .env in project root
if (file.exists(".env")) {
  readRenviron(".env")
}

suppressPackageStartupMessages({
  library(evd)
  library(DBI)
  library(RPostgres)
  library(dplyr)
})

cat("🔄 Connecting to PostgreSQL LiquidityRiskDB...\n")

# 1. Database Connection
db_host <- Sys.getenv("DB_HOST", "localhost")
db_port <- as.numeric(Sys.getenv("DB_PORT", 5432))
db_name <- Sys.getenv("DB_NAME", "LiquidityRiskDB")
db_user <- Sys.getenv("DB_USER", "postgres")
db_pass <- Sys.getenv("DB_PASSWORD")

con <- dbConnect(
  RPostgres::Postgres(),
  dbname = db_name,
  host = db_host,
  port = db_port,
  user = db_user,
  password = db_pass
)

# Auto-create EVT table if missing
create_table_sql <- "
  CREATE TABLE IF NOT EXISTS evt_liquidity_tail_risk (
      evt_id SERIAL PRIMARY KEY,
      calc_date DATE NOT NULL,
      threshold_u NUMERIC(15, 2) NOT NULL,
      gpd_shape_xi NUMERIC(8, 6) NOT NULL,
      gpd_scale_beta NUMERIC(12, 2) NOT NULL,
      evt_var_999_eur NUMERIC(15, 2) NOT NULL,
      evt_es_999_eur NUMERIC(15, 2) NOT NULL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      CONSTRAINT unique_evt_date UNIQUE (calc_date)
  );
"
dbExecute(con, create_table_sql)

# 2. Query Outflow Cash Flows
query <- "SELECT amount_eur FROM fact_cash_flows WHERE flow_type = 'Outflow';"
outflows_df <- dbGetQuery(con, query)

# Simulate 1,000 daily heavy-tailed liquidity outflow observations
set.seed(42)
base_outflows <- outflows_df$amount_eur
sim_outflows <- abs(rnorm(1000, mean = mean(base_outflows), sd = sd(base_outflows) * 1.5)) + 
  rexp(1000, rate = 1/5000000)  # Heavy exponential tail shock

cat(sprintf("✅ Generated %d daily liquidity outflow observations for EVT tail fitting.\n", length(sim_outflows)))

# 3. Fit Generalized Pareto Distribution (GPD) via Peaks-Over-Threshold (POT)
threshold_u <- quantile(sim_outflows, 0.90)  # 90th percentile threshold
exceedances <- sim_outflows[sim_outflows > threshold_u] - threshold_u

# Fit GPD model
fit_gpd <- fpot(sim_outflows, threshold = threshold_u, model = "gpd")

scale_beta <- as.numeric(fit_gpd$estimate["scale"])
shape_xi <- as.numeric(fit_gpd$estimate["shape"])

# 4. Calculate EVT-VaR (99.9%) and EVT Expected Shortfall (99.9%)
n <- length(sim_outflows)
n_u <- length(exceedances)
p <- 0.999  # 99.9% Extreme Confidence Level

# EVT-VaR 99.9% formula
evt_var_999 <- threshold_u + (scale_beta / shape_xi) * (((n / n_u) * (1 - p))^(-shape_xi) - 1)

# EVT Expected Shortfall 99.9% formula
evt_es_999 <- (evt_var_999 + scale_beta - shape_xi * threshold_u) / (1 - shape_xi)

calc_date <- format(Sys.Date(), "%Y-%m-%d")

cat("\n=======================================================\n")
cat("📊 EXTREME VALUE THEORY (EVT) LIQUIDITY TAIL RISK REPORT\n")
cat("=======================================================\n")
cat(sprintf("• High Threshold (u 90%%):            EUR %15.2f\n", threshold_u))
cat(sprintf("• GPD Shape Parameter (xi):               %15.6f (Heavy Tail)\n", shape_xi))
cat(sprintf("• GPD Scale Parameter (beta):             %15.2f\n", scale_beta))
cat(sprintf("• 99.9%% EVT Liquidity VaR:          EUR %15.2f\n", evt_var_999))
cat(sprintf("• 99.9%% EVT Tail Expected Shortfall: EUR %15.2f\n", evt_es_999))
cat("=======================================================\n\n")

# 5. Upload EVT Results to PostgreSQL
upsert_sql <- sprintf("
  INSERT INTO evt_liquidity_tail_risk (calc_date, threshold_u, gpd_shape_xi, gpd_scale_beta, evt_var_999_eur, evt_es_999_eur)
  VALUES ('%s', %.2f, %.6f, %.2f, %.2f, %.2f)
  ON CONFLICT (calc_date) DO UPDATE
  SET threshold_u = EXCLUDED.threshold_u,
      gpd_shape_xi = EXCLUDED.gpd_shape_xi,
      gpd_scale_beta = EXCLUDED.gpd_scale_beta,
      evt_var_999_eur = EXCLUDED.evt_var_999_eur,
      evt_es_999_eur = EXCLUDED.evt_es_999_eur;
", calc_date, threshold_u, shape_xi, scale_beta, evt_var_999, evt_es_999)

dbExecute(con, upsert_sql)
cat("🎉 EVT Liquidity Tail Risk metrics committed to PostgreSQL successfully!\n")

# Disconnect
dbDisconnect(con)

