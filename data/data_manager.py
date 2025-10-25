# data/data_manager.py

import aiosqlite
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import fields

from astrbot.api import logger
from astrbot.api.star import StarTools

from ..config_manager import ConfigManager
from ..models import Player, PlayerEffect, ActiveWorldBoss

class DataBase:
    """数据库管理器，封装所有数据库操作"""
    
    def __init__(self, db_file_name: str):
        data_dir = StarTools.get_data_dir("xiuxian")
        data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = data_dir / db_file_name
        self.conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        if self.conn is None:
            self.conn = await aiosqlite.connect(self.db_path)
            self.conn.row_factory = aiosqlite.Row
            logger.info(f"数据库连接已创建: {self.db_path}")

    async def close(self):
        if self.conn:
            await self.conn.close()
            self.conn = None
            logger.info("数据库连接已关闭。")

    async def get_active_bosses(self) -> List[ActiveWorldBoss]:
        async with self.conn.execute("SELECT * FROM active_world_bosses") as cursor:
            rows = await cursor.fetchall()
            return [ActiveWorldBoss(**dict(row)) for row in rows]

    async def create_active_boss(self, boss: ActiveWorldBoss):
        await self.conn.execute(
            "INSERT INTO active_world_bosses (boss_id, current_hp, max_hp, spawned_at, level_index) VALUES (?, ?, ?, ?, ?)",
            (boss.boss_id, boss.current_hp, boss.max_hp, boss.spawned_at, boss.level_index)
        )
        await self.conn.commit()

    async def update_active_boss_hp(self, boss_id: str, new_hp: int):
        await self.conn.execute(
            "UPDATE active_world_bosses SET current_hp = ? WHERE boss_id = ?",
            (new_hp, boss_id)
        )
        await self.conn.commit()

    async def delete_active_boss(self, boss_id: str):
        await self.conn.execute("DELETE FROM active_world_bosses WHERE boss_id = ?", (boss_id,))
        await self.conn.commit()

    async def record_boss_damage(self, boss_id: str, user_id: str, user_name: str, damage: int):
        await self.conn.execute("""
            INSERT INTO world_boss_participants (boss_id, user_id, user_name, total_damage) VALUES (?, ?, ?, ?)
            ON CONFLICT(boss_id, user_id) DO UPDATE SET total_damage = total_damage + excluded.total_damage;
        """, (boss_id, user_id, user_name, damage))
        await self.conn.commit()

    async def get_boss_participants(self, boss_id: str) -> List[Dict[str, Any]]:
        sql = "SELECT user_id, user_name, total_damage FROM world_boss_participants WHERE boss_id = ? ORDER BY total_damage DESC"
        async with self.conn.execute(sql, (boss_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def clear_boss_data(self, boss_id: str):
        try:
            await self.conn.execute("BEGIN")
            await self.conn.execute("DELETE FROM active_world_bosses WHERE boss_id = ?", (boss_id,))
            await self.conn.execute("DELETE FROM world_boss_participants WHERE boss_id = ?", (boss_id,))
            await self.conn.commit()
            logger.info(f"Boss {boss_id} 的数据已清理。")
        except aiosqlite.Error as e:
            await self.conn.rollback()
            logger.error(f"清理Boss {boss_id} 数据失败: {e}")

    async def get_top_players(self, limit: int) -> List[Player]:
        async with self.conn.execute(
            "SELECT * FROM players ORDER BY level_index DESC, experience DESC LIMIT ?", (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [Player(**dict(row)) for row in rows]

    async def get_all_players_avg_level(self) -> int:
        """获取所有玩家的平均境界level_index"""
        async with self.conn.execute("SELECT AVG(level_index) as avg_level FROM players") as cursor:
            row = await cursor.fetchone()
            if row and row['avg_level'] is not None:
                return max(1, int(row['avg_level']))  # 至少返回1
            return 1  # 如果没有玩家，返回1

    async def is_dao_name_taken(self, dao_name: str, exclude_user_id: Optional[str] = None) -> bool:
        """检查道号是否已被占用"""
        if exclude_user_id:
            async with self.conn.execute(
                "SELECT COUNT(*) FROM players WHERE dao_name = ? AND user_id != ?",
                (dao_name, exclude_user_id)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] > 0
        else:
            async with self.conn.execute(
                "SELECT COUNT(*) FROM players WHERE dao_name = ?",
                (dao_name,)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] > 0

    async def get_player_by_id(self, user_id: str) -> Optional[Player]:
        async with self.conn.execute("SELECT * FROM players WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return Player(**dict(row)) if row else None

    async def create_player(self, player: Player):
        player_fields = [f.name for f in fields(Player)]
        columns = ", ".join(player_fields)
        placeholders = ", ".join([f":{f}" for f in player_fields])
        sql = f"INSERT INTO players ({columns}) VALUES ({placeholders})"
        await self.conn.execute(sql, player.__dict__)
        await self.conn.commit()

    async def update_player(self, player: Player):
        player_fields = [f.name for f in fields(Player) if f.name != 'user_id']
        set_clause = ", ".join([f"{f} = :{f}" for f in player_fields])
        sql = f"UPDATE players SET {set_clause} WHERE user_id = :user_id"
        await self.conn.execute(sql, player.__dict__)
        await self.conn.commit()

    async def update_players_in_transaction(self, players: List[Player]):
        if not players:
            return
        player_fields = [f.name for f in fields(Player) if f.name != 'user_id']
        set_clause = ", ".join([f"{f} = :{f}" for f in player_fields])
        sql = f"UPDATE players SET {set_clause} WHERE user_id = :user_id"
        try:
            await self.conn.execute("BEGIN")
            for player in players:
                await self.conn.execute(sql, player.__dict__)
            await self.conn.commit()
        except aiosqlite.Error as e:
            await self.conn.rollback()
            logger.error(f"批量更新玩家事务失败: {e}")
            raise

    async def create_sect(self, sect_name: str, leader_id: str) -> int:
        async with self.conn.execute("INSERT INTO sects (name, leader_id) VALUES (?, ?)", (sect_name, leader_id)) as cursor:
            await self.conn.commit()
            return cursor.lastrowid

    async def delete_sect(self, sect_id: int):
        await self.conn.execute("DELETE FROM sects WHERE id = ?", (sect_id,))
        await self.conn.commit()

    async def get_sect_by_name(self, sect_name: str) -> Optional[Dict[str, Any]]:
        async with self.conn.execute("SELECT * FROM sects WHERE name = ?", (sect_name,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_sect_by_id(self, sect_id: int) -> Optional[Dict[str, Any]]:
        async with self.conn.execute("SELECT * FROM sects WHERE id = ?", (sect_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_sect_members(self, sect_id: int) -> List[Player]:
        async with self.conn.execute("SELECT * FROM players WHERE sect_id = ?", (sect_id,)) as cursor:
            rows = await cursor.fetchall()
            return [Player(**dict(row)) for row in rows]

    async def update_player_sect(self, user_id: str, sect_id: Optional[int], sect_name: Optional[str]):
        await self.conn.execute("UPDATE players SET sect_id = ?, sect_name = ? WHERE user_id = ?", (sect_id, sect_name, user_id))
        await self.conn.commit()

    async def get_inventory_by_user_id(self, user_id: str, config_manager: ConfigManager) -> List[Dict[str, Any]]:
        async with self.conn.execute("SELECT item_id, quantity FROM inventory WHERE user_id = ?", (user_id,)) as cursor:
            rows = await cursor.fetchall()
            inventory_list = []
            for row in rows:
                item_id, quantity = row['item_id'], row['quantity']
                item_info = config_manager.item_data.get(str(item_id))
                if item_info:
                     inventory_list.append({
                        "item_id": item_id, "name": item_info.name,
                        "quantity": quantity, "description": item_info.description,
                        "rank": item_info.rank, "type": item_info.type
                    })
                else:
                    inventory_list.append({
                        "item_id": item_id, "name": f"未知物品(ID:{item_id})",
                        "quantity": quantity, "description": "此物品信息已丢失",
                        "rank": "未知", "type": "未知"
                    })
            return inventory_list

    async def get_item_from_inventory(self, user_id: str, item_id: str) -> Optional[Dict[str, Any]]:
        async with self.conn.execute("SELECT item_id, quantity FROM inventory WHERE user_id = ? AND item_id = ?", (user_id, item_id)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def add_items_to_inventory_in_transaction(self, user_id: str, items: Dict[str, int]):
        try:
            await self.conn.execute("BEGIN")
            for item_id, quantity in items.items():
                await self.conn.execute("""
                    INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?)
                    ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + excluded.quantity;
                """, (user_id, item_id, quantity))
            await self.conn.commit()
        except aiosqlite.Error as e:
            await self.conn.rollback()
            logger.error(f"批量添加物品事务失败: {e}")
            raise

    async def remove_item_from_inventory(self, user_id: str, item_id: str, quantity: int = 1) -> bool:
        try:
            await self.conn.execute("BEGIN")
            cursor = await self.conn.execute("""
                UPDATE inventory SET quantity = quantity - ?
                WHERE user_id = ? AND item_id = ? AND quantity >= ?
            """, (quantity, user_id, item_id, quantity))

            if cursor.rowcount == 0:
                await self.conn.rollback()
                return False

            await self.conn.execute("DELETE FROM inventory WHERE user_id = ? AND item_id = ? AND quantity <= 0", (user_id, item_id))
            await self.conn.commit()
            return True
        except aiosqlite.Error as e:
            await self.conn.rollback()
            logger.error(f"移除物品事务失败: {e}")
            return False

    async def transactional_buy_item(self, user_id: str, item_id: str, quantity: int, total_cost: int) -> Tuple[bool, str]:
        try:
            await self.conn.execute("BEGIN")
            cursor = await self.conn.execute(
                "UPDATE players SET gold = gold - ? WHERE user_id = ? AND gold >= ?",
                (total_cost, user_id, total_cost)
            )
            if cursor.rowcount == 0:
                await self.conn.rollback()
                return False, "ERROR_INSUFFICIENT_FUNDS"

            await self.conn.execute("""
                INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?)
                ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + excluded.quantity;
            """, (user_id, item_id, quantity))

            await self.conn.commit()
            return True, "SUCCESS"
        except aiosqlite.Error as e:
            await self.conn.rollback()
            logger.error(f"购买物品事务失败: {e}")
            return False, "ERROR_DATABASE"

    async def transactional_apply_item_effect(self, user_id: str, item_id: str, quantity: int, effect: PlayerEffect, breakthrough_bonus: float = 0.0) -> bool:
        try:
            await self.conn.execute("BEGIN")
            cursor = await self.conn.execute(
                "UPDATE inventory SET quantity = quantity - ? WHERE user_id = ? AND item_id = ? AND quantity >= ?",
                (quantity, user_id, item_id, quantity)
            )
            if cursor.rowcount == 0:
                await self.conn.rollback()
                return False

            await self.conn.execute("DELETE FROM inventory WHERE user_id = ? AND item_id = ? AND quantity <= 0", (user_id, item_id))

            await self.conn.execute(
                """
                UPDATE players
                SET experience = experience + ?,
                    gold = gold + ?,
                    hp = MIN(max_hp + ?, hp + ?),
                    max_hp = max_hp + ?,
                    spiritual_power = spiritual_power + ?,
                    mental_power = mental_power + ?,
                    attack = attack + ?,
                    defense = defense + ?,
                    breakthrough_bonus = ?
                WHERE user_id = ?
                """,
                (effect.experience, effect.gold, effect.max_hp, effect.hp, 
                 effect.max_hp, effect.spiritual_power, effect.mental_power,
                 effect.attack, effect.defense, breakthrough_bonus, user_id)
            )
            await self.conn.commit()
            return True
        except aiosqlite.Error as e:
            await self.conn.rollback()
            logger.error(f"使用物品事务失败: {e}")
            return False

    async def get_shop_inventory(self, date: str) -> Dict[str, int]:
        """获取指定日期的商店库存"""
        async with self.conn.execute("SELECT item_id, stock FROM shop_inventory WHERE date = ?", (date,)) as cursor:
            rows = await cursor.fetchall()
            return {row['item_id']: row['stock'] for row in rows}

    async def init_shop_inventory(self, date: str, inventory_dict: Dict[str, int]):
        """初始化指定日期的商店库存（批量插入）"""
        try:
            await self.conn.execute("BEGIN")
            for item_id, stock in inventory_dict.items():
                await self.conn.execute("""
                    INSERT INTO shop_inventory (date, item_id, stock) VALUES (?, ?, ?)
                    ON CONFLICT(date, item_id) DO UPDATE SET stock = excluded.stock
                """, (date, item_id, stock))
            await self.conn.commit()
        except aiosqlite.Error as e:
            await self.conn.rollback()
            logger.error(f"初始化商店库存失败: {e}")
            raise

    async def get_shop_stock(self, date: str, item_id: str) -> Optional[int]:
        """获取指定日期某个物品的库存数量"""
        async with self.conn.execute(
            "SELECT stock FROM shop_inventory WHERE date = ? AND item_id = ?", 
            (date, item_id)
        ) as cursor:
            row = await cursor.fetchone()
            return row['stock'] if row else None

    async def decrease_shop_stock(self, date: str, item_id: str, quantity: int) -> bool:
        """减少商店库存，返回是否成功"""
        try:
            await self.conn.execute("BEGIN")
            cursor = await self.conn.execute("""
                UPDATE shop_inventory SET stock = stock - ?
                WHERE date = ? AND item_id = ? AND stock >= ?
            """, (quantity, date, item_id, quantity))
            
            if cursor.rowcount == 0:
                await self.conn.rollback()
                return False
            
            await self.conn.commit()
            return True
        except aiosqlite.Error as e:
            await self.conn.rollback()
            logger.error(f"减少商店库存失败: {e}")
            return False

    async def set_boss_cooldown(self, boss_id: str, defeated_at: float, respawn_at: float):
        """设置Boss冷却时间"""
        await self.conn.execute("""
            INSERT INTO boss_cooldowns (boss_id, defeated_at, respawn_at) VALUES (?, ?, ?)
            ON CONFLICT(boss_id) DO UPDATE SET defeated_at = excluded.defeated_at, respawn_at = excluded.respawn_at
        """, (boss_id, defeated_at, respawn_at))
        await self.conn.commit()

    async def get_boss_cooldown(self, boss_id: str) -> Optional[Dict[str, float]]:
        """获取Boss冷却信息"""
        async with self.conn.execute(
            "SELECT defeated_at, respawn_at FROM boss_cooldowns WHERE boss_id = ?",
            (boss_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"defeated_at": row['defeated_at'], "respawn_at": row['respawn_at']}
            return None

    async def remove_boss_cooldown(self, boss_id: str):
        """删除Boss冷却记录（Boss重生后清除）"""
        await self.conn.execute("DELETE FROM boss_cooldowns WHERE boss_id = ?", (boss_id,))
        await self.conn.commit()

    async def get_all_boss_cooldowns(self) -> Dict[str, Dict[str, float]]:
        """获取所有Boss的冷却信息"""
        async with self.conn.execute("SELECT boss_id, defeated_at, respawn_at FROM boss_cooldowns") as cursor:
            rows = await cursor.fetchall()
            return {
                row['boss_id']: {
                    "defeated_at": row['defeated_at'],
                    "respawn_at": row['respawn_at']
                }
                for row in rows
            }

    # ==================== 钱庄相关 ====================
    
    async def create_fixed_deposit(self, user_id: str, amount: int, duration_hours: int, deposit_time: float, mature_time: float) -> int:
        """创建定期存款"""
        async with self.conn.execute("""
            INSERT INTO fixed_deposits (user_id, amount, deposit_time, mature_time, duration_hours)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, amount, deposit_time, mature_time, duration_hours)) as cursor:
            await self.conn.commit()
            return cursor.lastrowid

    async def get_fixed_deposits(self, user_id: str) -> List[Dict]:
        """获取用户的所有定期存款"""
        async with self.conn.execute(
            "SELECT * FROM fixed_deposits WHERE user_id = ? ORDER BY mature_time",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_fixed_deposit_by_id(self, deposit_id: int) -> Optional[Dict]:
        """根据ID获取定期存款"""
        async with self.conn.execute(
            "SELECT * FROM fixed_deposits WHERE id = ?",
            (deposit_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def delete_fixed_deposit(self, deposit_id: int):
        """删除定期存款（取款后）"""
        await self.conn.execute("DELETE FROM fixed_deposits WHERE id = ?", (deposit_id,))
        await self.conn.commit()

    async def create_or_update_current_deposit(self, user_id: str, amount: int, deposit_time: float):
        """创建或更新活期存款"""
        await self.conn.execute("""
            INSERT INTO current_deposits (user_id, amount, deposit_time)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET 
                amount = amount + excluded.amount,
                deposit_time = excluded.deposit_time
        """, (user_id, amount, deposit_time))
        await self.conn.commit()

    async def get_current_deposit(self, user_id: str) -> Optional[Dict]:
        """获取用户的活期存款"""
        async with self.conn.execute(
            "SELECT * FROM current_deposits WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def delete_current_deposit(self, user_id: str):
        """删除活期存款（取款后）"""
        await self.conn.execute("DELETE FROM current_deposits WHERE user_id = ?", (user_id,))
        await self.conn.commit()

    async def update_current_deposit_amount(self, user_id: str, new_amount: int, new_deposit_time: float):
        """更新活期存款金额（部分取款）"""
        await self.conn.execute("""
            UPDATE current_deposits SET amount = ?, deposit_time = ?
            WHERE user_id = ?
        """, (new_amount, new_deposit_time, user_id))
        await self.conn.commit()