import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from sqlalchemy import create_engine
from config.config import DATABASE_URL

def get_db_engine():
    """Returns SQLAlchemy Database Engine for LiquidityRiskDB."""
    try:
        engine = create_engine(DATABASE_URL, echo=False)
        return engine
    except Exception as e:
        print(f"❌ Connection error: {e}")
        raise e

if __name__ == "__main__":
    engine = get_db_engine()
    with engine.connect() as conn:
        print("✅ Successfully connected to PostgreSQL LiquidityRiskDB!")