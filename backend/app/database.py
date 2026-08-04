import asyncio
import asyncpg
from .config import settings

async def get_pool():
    return await asyncpg.create_pool(dsn=settings.database_url)

# helper to ensure table exists
essync def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS players (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
            );
        ''')
    await pool.close()

# Run init on import in serverless may be optional
try:
    asyncio.get_event_loop().run_until_complete(init_db())
except Exception:
    pass
