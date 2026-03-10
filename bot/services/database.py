import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional


@dataclass
class User:
    telegram_id: int
    username: Optional[str]
    created_at: str
    is_active: bool


@dataclass
class Subscription:
    id: int
    telegram_id: int
    email: str
    uuid: str
    device_type: str
    flow: str
    expires_at: Optional[str]
    is_active: bool
    created_at: str


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    
    def _get_conn(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active INTEGER DEFAULT 1
                );
                
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER,
                    email TEXT UNIQUE,
                    uuid TEXT UNIQUE,
                    device_type TEXT,
                    flow TEXT DEFAULT 'xtls-rprx-vision',
                    expires_at TIMESTAMP,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER,
                    amount REAL,
                    currency TEXT,
                    period_months INTEGER,
                    status TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS admin_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER,
                    action TEXT,
                    target_user INTEGER,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """
            )

    def get_or_create_user(
        self, telegram_id: int, username: Optional[str] = None
    ) -> User:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT telegram_id, username, created_at, is_active FROM users WHERE telegram_id = ?",
                (telegram_id,),
            )
            row = cursor.fetchone()

            if row:
                return User(*row)

            cursor.execute(
                "INSERT INTO users (telegram_id, username) VALUES (?, ?)",
                (telegram_id, username),
            )
            conn.commit()

            return User(telegram_id, username, datetime.now().isoformat(), True)

    def add_subscription(
        self,
        telegram_id: int,
        email: str,
        uuid: str,
        device_type: str,
        flow: str = "xtls-rprx-vision",
        expires_at: Optional[datetime] = None,
    ) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            expires_str = expires_at.isoformat() if expires_at else None

            cursor.execute(
                """
                INSERT INTO subscriptions (telegram_id, email, uuid, device_type, flow, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (telegram_id, email, uuid, device_type, flow, expires_str),
            )

            conn.commit()
            return cursor.lastrowid

    def get_user_subscriptions(
        self, telegram_id: int, active_only: bool = True
    ) -> List[Subscription]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            query = """
                SELECT id, telegram_id, email, uuid, device_type, flow, expires_at, is_active, created_at
                FROM subscriptions WHERE telegram_id = ?
            """
            if active_only:
                query += " AND is_active = 1 AND (expires_at IS NULL OR expires_at > ?)"
                cursor.execute(query, (telegram_id, datetime.now().isoformat()))
            else:
                cursor.execute(query, (telegram_id,))

            rows = cursor.fetchall()
            return [Subscription(*row) for row in rows]

    def get_subscription_by_email(self, email: str) -> Optional[Subscription]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, telegram_id, email, uuid, device_type, flow, expires_at, is_active, created_at
                FROM subscriptions WHERE email = ?
            """,
                (email,),
            )
            row = cursor.fetchone()
            return Subscription(*row) if row else None

    def deactivate_subscription(self, email: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE subscriptions SET is_active = 0 WHERE email = ?", (email,)
            )
            conn.commit()

    def extend_subscription(self, email: str, new_expires: datetime):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE subscriptions SET expires_at = ?, is_active = 1 WHERE email = ?",
                (new_expires.isoformat(), email),
            )
            conn.commit()

    def add_payment(
        self,
        telegram_id: int,
        amount: float,
        currency: str,
        period_months: int,
        status: str = "pending",
    ):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO payments (telegram_id, amount, currency, period_months, status)
                VALUES (?, ?, ?, ?, ?)
            """,
                (telegram_id, amount, currency, period_months, status),
            )
            conn.commit()

    def update_payment_status(self, payment_id: int, status: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE payments SET status = ? WHERE id = ?", (status, payment_id)
            )
            conn.commit()

    def get_stats(self) -> Dict:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM subscriptions WHERE is_active = 1")
            active_subs = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT COUNT(*) FROM subscriptions 
                WHERE is_active = 1 AND expires_at > ?
            """,
                (datetime.now().isoformat(),),
            )
            paid_subs = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT SUM(amount) FROM payments WHERE status = 'completed'
            """
            )
            total_revenue = cursor.fetchone()[0] or 0

            return {
                "total_users": total_users,
                "active_subscriptions": active_subs,
                "paid_subscriptions": paid_subs,
                "total_revenue": total_revenue,
            }

    def get_all_users(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT u.telegram_id, u.username, u.created_at,
                       COUNT(s.id) as sub_count,
                       MAX(s.expires_at) as max_expiry
                FROM users u
                LEFT JOIN subscriptions s ON u.telegram_id = s.telegram_id AND s.is_active = 1
                GROUP BY u.telegram_id
                ORDER BY u.created_at DESC
                LIMIT ? OFFSET ?
            """,
                (limit, offset),
            )

            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def log_admin_action(
        self,
        admin_id: int,
        action: str,
        target_user: Optional[int] = None,
        details: Optional[str] = None,
    ):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO admin_actions (admin_id, action, target_user, details)
                VALUES (?, ?, ?, ?)
            """,
                (admin_id, action, target_user, details),
            )
            conn.commit()
