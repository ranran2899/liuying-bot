"""账号存储：SQLite + PBKDF2 口令散列。

只依赖标准库 `sqlite3`，所有阻塞调用通过 `asyncio.to_thread` 放到线程池，
避免阻塞事件循环。
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

PBKDF2_ROUNDS = 200_000


@dataclass(slots=True)
class Account:
    uid: int
    username: str
    nickname: str
    created_at: int
    last_login: int
    #: 玩家档案（逃脱次数、最好成绩等）
    escapes: int = 0
    deaths: int = 0
    best_time: float = -1.0

    def profile(self) -> dict[str, object]:
        return {
            "uid": self.uid,
            "username": self.username,
            "name": self.nickname,
            "escapes": self.escapes,
            "deaths": self.deaths,
            "best_time": self.best_time,
        }


class AccountStore:
    """账号与令牌的持久化。"""

    def __init__(self, db_path: str) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ 建表
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_sync(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    uid        INTEGER PRIMARY KEY AUTOINCREMENT,
                    username   TEXT    NOT NULL UNIQUE,
                    nickname   TEXT    NOT NULL,
                    salt       BLOB    NOT NULL,
                    pwd_hash   BLOB    NOT NULL,
                    created_at INTEGER NOT NULL,
                    last_login INTEGER NOT NULL DEFAULT 0,
                    escapes    INTEGER NOT NULL DEFAULT 0,
                    deaths     INTEGER NOT NULL DEFAULT 0,
                    best_time  REAL    NOT NULL DEFAULT -1.0
                );
                CREATE TABLE IF NOT EXISTS tokens (
                    token      TEXT    PRIMARY KEY,
                    uid        INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tokens_uid ON tokens(uid);
                """
            )

    async def init(self) -> None:
        await asyncio.to_thread(self._init_sync)

    # ------------------------------------------------------------------ 口令
    @staticmethod
    def hash_password(password: str, salt: bytes) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)

    # ------------------------------------------------------------------ 注册
    def _register_sync(self, username: str, password: str, nickname: str) -> Account | None:
        salt = os.urandom(16)
        pwd_hash = self.hash_password(password, salt)
        now = int(time.time())
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    "INSERT INTO accounts(username, nickname, salt, pwd_hash, created_at)"
                    " VALUES(?,?,?,?,?)",
                    (username, nickname, salt, pwd_hash, now),
                )
                uid = int(cur.lastrowid or 0)
        except sqlite3.IntegrityError:
            return None
        return Account(uid=uid, username=username, nickname=nickname, created_at=now,
                       last_login=now)

    async def register(self, username: str, password: str, nickname: str) -> Account | None:
        """注册；用户名已存在返回 None。"""
        async with self._lock:
            return await asyncio.to_thread(self._register_sync, username, password, nickname)

    # ------------------------------------------------------------------ 登录
    def _verify_sync(self, username: str, password: str) -> Account | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM accounts WHERE username=?", (username,)).fetchone()
            if row is None:
                return None
            expect = bytes(row["pwd_hash"])
            actual = self.hash_password(password, bytes(row["salt"]))
            if not secrets.compare_digest(expect, actual):
                return None
            now = int(time.time())
            conn.execute("UPDATE accounts SET last_login=? WHERE uid=?", (now, row["uid"]))
            return _row_to_account(row, last_login=now)

    async def verify(self, username: str, password: str) -> Account | None:
        return await asyncio.to_thread(self._verify_sync, username, password)

    # ------------------------------------------------------------------ 令牌
    def _issue_token_sync(self, uid: int, ttl: int) -> str:
        token = secrets.token_urlsafe(32)
        expires = int(time.time()) + ttl
        with self._connect() as conn:
            conn.execute("DELETE FROM tokens WHERE expires_at < ?", (int(time.time()),))
            conn.execute("INSERT INTO tokens(token, uid, expires_at) VALUES(?,?,?)",
                         (token, uid, expires))
        return token

    async def issue_token(self, uid: int, ttl: int) -> str:
        return await asyncio.to_thread(self._issue_token_sync, uid, ttl)

    def _resolve_token_sync(self, token: str) -> Account | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT a.* FROM tokens t JOIN accounts a ON a.uid=t.uid"
                " WHERE t.token=? AND t.expires_at > ?",
                (token, int(time.time())),
            ).fetchone()
            return _row_to_account(row) if row is not None else None

    async def resolve_token(self, token: str) -> Account | None:
        return await asyncio.to_thread(self._resolve_token_sync, token)

    def _revoke_sync(self, token: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM tokens WHERE token=?", (token,))

    async def revoke_token(self, token: str) -> None:
        await asyncio.to_thread(self._revoke_sync, token)

    # ------------------------------------------------------------------ 资料
    def _rename_sync(self, uid: int, nickname: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE accounts SET nickname=? WHERE uid=?", (nickname, uid))

    async def rename(self, uid: int, nickname: str) -> None:
        await asyncio.to_thread(self._rename_sync, uid, nickname)

    def _record_sync(self, uid: int, escaped: bool, survive_time: float) -> None:
        with self._connect() as conn:
            if escaped:
                conn.execute(
                    "UPDATE accounts SET escapes = escapes + 1,"
                    " best_time = CASE WHEN best_time < 0 OR ? < best_time THEN ? ELSE best_time END"
                    " WHERE uid=?",
                    (survive_time, survive_time, uid),
                )
            else:
                conn.execute("UPDATE accounts SET deaths = deaths + 1 WHERE uid=?", (uid,))

    async def record_result(self, uid: int, escaped: bool, survive_time: float) -> None:
        await asyncio.to_thread(self._record_sync, uid, escaped, survive_time)


def _row_to_account(row: sqlite3.Row, last_login: int | None = None) -> Account:
    return Account(
        uid=int(row["uid"]),
        username=str(row["username"]),
        nickname=str(row["nickname"]),
        created_at=int(row["created_at"]),
        last_login=last_login if last_login is not None else int(row["last_login"]),
        escapes=int(row["escapes"]),
        deaths=int(row["deaths"]),
        best_time=float(row["best_time"]),
    )
