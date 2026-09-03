import json
import asyncpg
from .config import settings


async def get_pool():
    return await asyncpg.create_pool(dsn=settings.database_url, min_size=1, max_size=5)


async def init_db():
    from .routes import GAME_CONFIGS

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
                    personal_info TEXT,
                    clues JSONB DEFAULT '[]'::jsonb,
                    game_preset TEXT DEFAULT 'murder_mystery',
                    status TEXT DEFAULT 'registered',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
                );
                '''
            )
            legacy_poll = await conn.fetchval("SELECT 1 FROM information_schema.columns WHERE table_name='poll_votes' AND column_name='game_preset'")
            if legacy_poll:
                await conn.execute('ALTER TABLE poll_votes RENAME TO poll_votes_legacy')
            await conn.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS role TEXT")
            await conn.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS target TEXT")
            await conn.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS secret_info TEXT")
            await conn.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS personal_info TEXT")
            await conn.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS clues JSONB DEFAULT '[]'::jsonb")
            await conn.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS game_preset TEXT DEFAULT 'murder_mystery'")
            await conn.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'registered'")
            await conn.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()")
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
            await conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS game_configs (
                    id TEXT PRIMARY KEY,
                    config JSONB NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS generated_games (
                    id UUID PRIMARY KEY,
                    game_preset TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS generated_player_data (
                    id SERIAL PRIMARY KEY,
                    generated_game_id UUID NOT NULL REFERENCES generated_games(id) ON DELETE CASCADE,
                    player_id TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    UNIQUE (generated_game_id, player_id)
                );
                CREATE TABLE IF NOT EXISTS polls (
                    id SERIAL PRIMARY KEY,
                    question TEXT NOT NULL,
                    active BOOLEAN DEFAULT FALSE,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS poll_options (
                    id SERIAL PRIMARY KEY,
                    poll_id INTEGER NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
                    label TEXT NOT NULL,
                    sort_order INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS poll_votes (
                    id SERIAL PRIMARY KEY,
                    poll_id INTEGER NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
                    option_id INTEGER NOT NULL REFERENCES poll_options(id) ON DELETE CASCADE,
                    voter_hash TEXT NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                    UNIQUE (poll_id, voter_hash)
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
            await conn.executemany(
                'INSERT INTO game_configs(id, config) VALUES($1, $2) ON CONFLICT (id) DO UPDATE SET config=EXCLUDED.config, updated_at=now()',
                [(preset_id, json.dumps(config)) for preset_id, config in GAME_CONFIGS.items()],
            )
            await conn.execute("ALTER TABLE game_state ADD COLUMN IF NOT EXISTS voting_active BOOLEAN DEFAULT FALSE")
            poll_id = await conn.fetchval('SELECT id FROM polls ORDER BY id LIMIT 1')
            if poll_id is None:
                poll_id = await conn.fetchval("INSERT INTO polls(question, active) VALUES($1, FALSE) RETURNING id", 'Welke game spreekt je het meest aan?')
                await conn.executemany(
                    'INSERT INTO poll_options(poll_id, label, sort_order) VALUES($1, $2, $3)',
                    [(poll_id, 'Murder Mystery', 0), (poll_id, 'The Heist', 1), (poll_id, 'The Investigation', 2)],
                )
    finally:
        await pool.close()
