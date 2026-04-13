import aiosqlite

DATABASE_NAME = "bot_data.db"

async def init_db():
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                phone TEXT NOT NULL,
                token TEXT NOT NULL,
                alias TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, phone)
            );
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_states (
                user_id INTEGER PRIMARY KEY,
                state TEXT,
                data TEXT
            );
        """)
        await db.commit()

async def add_user(user_id, first_name, username):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id, first_name, username) VALUES (?, ?, ?)",
                         (user_id, first_name, username))
        await db.commit()

async def add_account(user_id, phone, token, alias=None):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO accounts (user_id, phone, token, alias) VALUES (?, ?, ?, ?)",
                         (user_id, phone, token, alias))
        await db.commit()

async def get_accounts(user_id):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute("SELECT id, phone, alias, token FROM accounts WHERE user_id = ?", (user_id,))
        accounts = await cursor.fetchall()
        return accounts

async def get_account_by_id(account_id, user_id):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute("SELECT id, phone, alias, token FROM accounts WHERE id = ? AND user_id = ?", (account_id, user_id))
        account = await cursor.fetchone()
        return account

async def delete_account(account_id, user_id):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute("DELETE FROM accounts WHERE id = ? AND user_id = ?", (account_id, user_id))
        await db.commit()

async def update_account_token(account_id, user_id, new_token):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute("UPDATE accounts SET token = ? WHERE id = ? AND user_id = ?", (new_token, account_id, user_id))
        await db.commit()

async def set_user_state(user_id, state, data=None):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO user_states (user_id, state, data) VALUES (?, ?, ?)",
                         (user_id, state, data))
        await db.commit()

async def get_user_state(user_id):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute("SELECT state, data FROM user_states WHERE user_id = ?", (user_id,))
        state = await cursor.fetchone()
        return state

async def delete_user_state(user_id):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute("DELETE FROM user_states WHERE user_id = ?", (user_id,))
        await db.commit()
