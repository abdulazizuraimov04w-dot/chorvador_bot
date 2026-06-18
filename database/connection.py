import os
import asyncio
import asyncpg
from dotenv import load_dotenv
from utils.logger import logger

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(dotenv_path)

DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "dairy_delivery_db")

# Connection pool instance
_pool = None

async def init_db_pool():
    """Initializes the asyncpg connection pool."""
    global _pool
    if _pool is not None:
        return _pool

    logger.info("Initializing PostgreSQL connection pool...")
    try:
        _pool = await asyncpg.create_pool(
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=int(DB_PORT),
            database=DB_NAME,
            min_size=2,
            max_size=20,
            max_inactive_connection_lifetime=300.0
        )
        logger.info("PostgreSQL connection pool initialized successfully.")
        return _pool
    except Exception as e:
        logger.error(f"Failed to initialize PostgreSQL pool: {e}")
        raise e

async def close_db_pool():
    """Closes the connection pool."""
    global _pool
    if _pool is not None:
        logger.info("Closing PostgreSQL connection pool...")
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL connection pool closed.")

def get_pool():
    """Returns the active database pool."""
    if _pool is None:
        raise RuntimeError("Database pool has not been initialized. Call init_db_pool() first.")
    return _pool

async def execute_query(query: str, *args):
    """Executes a non-returning query (INSERT, UPDATE, DELETE)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            return await conn.execute(query, *args)
        except Exception as e:
            logger.error(f"Error executing query: {query} with args {args}. Exception: {e}")
            raise e

async def fetch_rows(query: str, *args):
    """Fetches multiple rows (SELECT)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            return await conn.fetch(query, *args)
        except Exception as e:
            logger.error(f"Error fetching rows: {query} with args {args}. Exception: {e}")
            raise e

async def fetch_row(query: str, *args):
    """Fetches a single row (SELECT ... LIMIT 1)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            return await conn.fetchrow(query, *args)
        except Exception as e:
            logger.error(f"Error fetching single row: {query} with args {args}. Exception: {e}")
            raise e

async def fetch_val(query: str, *args):
    """Fetches a single value (e.g. SELECT count(*))."""
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            return await conn.fetchval(query, *args)
        except Exception as e:
            logger.error(f"Error fetching value: {query} with args {args}. Exception: {e}")
            raise e
