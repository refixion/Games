import asyncio
import asyncpg
from .config import settings


async def get_pool():
    return await asyncpg.create_pool(dsn=settings.database_url, min_size=1, max_size=5)


async def init_db():
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS players (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    role TEXT,
                    target TEXT,
                    secret_info TEXT,
                    game_preset TEXT DEFAULT 'murder_mystery',
                    status TEXT DEFAULT 'registered',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
                );
                '''
            )
            await conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS game_state (
                    id SERIAL PRIMARY KEY,
                    game_name TEXT NOT NULL DEFAULT 'Secret Game',
                    game_preset TEXT DEFAULT 'murder_mystery',
                    registration_open BOOLEAN DEFAULT TRUE,
                    voting_active BOOLEAN DEFAULT FALSE,
                    status TEXT DEFAULT 'draft',
                    theme JSONB DEFAULT '{}'::jsonb,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
                );
                '''
            )
            row = await conn.fetchrow('SELECT 1 FROM game_state LIMIT 1')
            if row is None:
                await conn.execute(
                    '''
                    INSERT INTO game_state (game_name, game_preset, registration_open, voting_active, status)
                    VALUES ($1, $2, $3, $4, $5)
                    ''',
                    'Secret Game',
                    'murder_mystery',
                    True,
                    False,
                    'draft',
                )
    finally:
        await pool.close()


try:
    asyncio.get_event_loop().run_until_complete(init_db())
except Exception:
    pass
