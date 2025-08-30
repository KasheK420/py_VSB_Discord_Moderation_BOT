# bot/database/queries/shop_queries.py
from __future__ import annotations
import asyncpg
from typing import List, Dict, Any, Optional

class ShopQueries:
    @staticmethod
    async def ensure_schema(pool: asyncpg.Pool) -> None:
        async with pool.acquire() as conn:
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS shop_items(
              id BIGSERIAL PRIMARY KEY,
              name TEXT NOT NULL,
              price INT NOT NULL CHECK (price >= 0),
              stock INT NOT NULL DEFAULT 0,
              description TEXT,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """)
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS shop_orders(
              id BIGSERIAL PRIMARY KEY,
              user_id BIGINT NOT NULL,
              item_id BIGINT NOT NULL REFERENCES shop_items(id),
              qty INT NOT NULL CHECK (qty > 0),
              total_price INT NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_shop_orders_user_at ON shop_orders(user_id, created_at desc);")

    @staticmethod
    async def add_item(pool: asyncpg.Pool, name: str, price: int, stock: int, description: str | None) -> int:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
            INSERT INTO shop_items(name, price, stock, description)
            VALUES ($1,$2,$3,$4) RETURNING id
            """, name, price, stock, description)
            return int(row["id"])

    @staticmethod
    async def list_items(pool: asyncpg.Pool) -> List[Dict[str, Any]]:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT id,name,price,stock,description FROM shop_items ORDER BY id asc")
        return [dict(r) for r in rows]

    @staticmethod
    async def get_item(pool: asyncpg.Pool, item_id: int) -> Optional[Dict[str, Any]]:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT id,name,price,stock,description FROM shop_items WHERE id=$1", item_id)
        return dict(row) if row else None

    @staticmethod
    async def purchase(pool: asyncpg.Pool, user_id: int, item_id: int, qty: int) -> Dict[str, Any]:
        if qty <= 0:
            raise ValueError("qty must be > 0")
        async with pool.acquire() as conn:
            async with conn.transaction():
                item = await conn.fetchrow("SELECT id,name,price,stock FROM shop_items WHERE id=$1 FOR UPDATE", item_id)
                if not item:
                    raise ValueError("Item not found")
                if item["stock"] < qty:
                    raise ValueError("Insufficient stock")
                total = int(item["price"]) * qty
                # reduce stock
                await conn.execute("UPDATE shop_items SET stock = stock - $2, updated_at=now() WHERE id=$1", item_id, qty)
                # record order
                row = await conn.fetchrow("""
                INSERT INTO shop_orders(user_id,item_id,qty,total_price)
                VALUES ($1,$2,$3,$4) RETURNING id
                """, user_id, item_id, qty, total)
                order_id = int(row["id"])
                return {"order_id": order_id, "item": dict(item), "qty": qty, "total": total}
