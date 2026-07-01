import aiosqlite
import os

DB_PATH = os.getenv("DB_PATH", "loans.db")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                discord_id  TEXT PRIMARY KEY,
                username    TEXT NOT NULL,
                reminder_enabled  INTEGER DEFAULT 1,
                reminder_days     INTEGER DEFAULT 7
            );

            CREATE TABLE IF NOT EXISTS loans (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id    TEXT NOT NULL,
                lender_id   TEXT NOT NULL,
                borrower_id TEXT NOT NULL,
                card_name   TEXT NOT NULL,
                quantity    INTEGER DEFAULT 1,
                note        TEXT,
                borrowed_at TEXT NOT NULL DEFAULT (datetime('now')),
                returned_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_loans_lender   ON loans(lender_id);
            CREATE INDEX IF NOT EXISTS idx_loans_borrower ON loans(borrower_id);
            CREATE INDEX IF NOT EXISTS idx_loans_guild    ON loans(guild_id);
        """)
        await db.commit()


async def upsert_user(discord_id: str, username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO users(discord_id, username) VALUES(?,?)
               ON CONFLICT(discord_id) DO UPDATE SET username=excluded.username""",
            (discord_id, username),
        )
        await db.commit()


async def get_user(discord_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE discord_id=?", (discord_id,)
        ) as cur:
            return await cur.fetchone()


async def add_loan(guild_id, lender_id, borrower_id, card_name, quantity, note):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO loans(guild_id, lender_id, borrower_id, card_name, quantity, note)
               VALUES(?,?,?,?,?,?)""",
            (guild_id, lender_id, borrower_id, card_name, quantity, note),
        )
        await db.commit()


async def get_active_loans_by_borrower(borrower_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT l.*, u.username AS lender_name
               FROM loans l JOIN users u ON u.discord_id = l.lender_id
               WHERE l.borrower_id=? AND l.returned_at IS NULL
               ORDER BY l.borrowed_at""",
            (borrower_id,),
        ) as cur:
            return await cur.fetchall()


async def get_active_loans_by_lender(lender_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT l.*, u.username AS borrower_name
               FROM loans l JOIN users u ON u.discord_id = l.borrower_id
               WHERE l.lender_id=? AND l.returned_at IS NULL
               ORDER BY l.borrowed_at""",
            (lender_id,),
        ) as cur:
            return await cur.fetchall()


async def get_loans_between(user_a: str, user_b: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT l.*,
                      ul.username AS lender_name,
                      ub.username AS borrower_name
               FROM loans l
               JOIN users ul ON ul.discord_id = l.lender_id
               JOIN users ub ON ub.discord_id = l.borrower_id
               WHERE l.returned_at IS NULL
                 AND ((l.lender_id=? AND l.borrower_id=?)
                   OR (l.lender_id=? AND l.borrower_id=?))
               ORDER BY l.borrowed_at""",
            (user_a, user_b, user_b, user_a),
        ) as cur:
            return await cur.fetchall()


async def get_all_active_loans(guild_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT l.*,
                      ul.username AS lender_name,
                      ub.username AS borrower_name
               FROM loans l
               JOIN users ul ON ul.discord_id = l.lender_id
               JOIN users ub ON ub.discord_id = l.borrower_id
               WHERE l.guild_id=? AND l.returned_at IS NULL
               ORDER BY l.borrowed_at""",
            (guild_id,),
        ) as cur:
            return await cur.fetchall()


async def return_loan(loan_id: int, borrower_id: str) -> bool:
    """Mark loan returned. Returns False if not found / not owned by borrower."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """UPDATE loans SET returned_at=datetime('now')
               WHERE id=? AND borrower_id=? AND returned_at IS NULL""",
            (loan_id, borrower_id),
        )
        await db.commit()
        return cur.rowcount > 0


async def get_overdue_loans(days: int):
    """Return active loans older than `days` days, grouped by borrower."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT l.*,
                      ul.username AS lender_name,
                      ub.username AS borrower_name,
                      u.reminder_enabled,
                      u.reminder_days
               FROM loans l
               JOIN users ul ON ul.discord_id = l.lender_id
               JOIN users ub ON ub.discord_id = l.borrower_id
               JOIN users u  ON u.discord_id  = l.borrower_id
               WHERE l.returned_at IS NULL
                 AND u.reminder_enabled = 1
                 AND julianday('now') - julianday(l.borrowed_at) >= u.reminder_days
               ORDER BY l.borrower_id, l.borrowed_at""",
        ) as cur:
            return await cur.fetchall()


async def set_reminder(discord_id: str, enabled: bool, days: int | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        if days is not None:
            await db.execute(
                "UPDATE users SET reminder_enabled=?, reminder_days=? WHERE discord_id=?",
                (int(enabled), days, discord_id),
            )
        else:
            await db.execute(
                "UPDATE users SET reminder_enabled=? WHERE discord_id=?",
                (int(enabled), discord_id),
            )
        await db.commit()


async def get_card_autocomplete(partial: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT DISTINCT card_name FROM loans
               WHERE card_name LIKE ? LIMIT 25""",
            (f"%{partial}%",),
        ) as cur:
            rows = await cur.fetchall()
            return [r[0] for r in rows]
