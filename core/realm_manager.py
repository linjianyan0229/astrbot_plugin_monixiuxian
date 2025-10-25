# core/realm_manager.py
import random
import time
from typing import Tuple, Dict, Any, List, Optional

from astrbot.api import logger, AstrBotConfig
from ..models import Player, FloorEvent, RealmInstance
from ..config_manager import ConfigManager
from ..data import DataBase
from .combat_manager import BattleManager, MonsterGenerator

class RealmGenerator:
    """秘境生成器"""
    
    @staticmethod
    def generate_for_player(player: Player, config: AstrBotConfig, config_manager: ConfigManager) -> Optional[RealmInstance]:
        level_index = player.level_index

        total_floors = config["REALM_RULES"]["REALM_BASE_FLOORS"] + \
                       (level_index // config["REALM_RULES"]["REALM_FLOORS_PER_LEVEL_DIVISOR"])

        monster_pool = list(config_manager.monster_data.keys())
        boss_pool = list(config_manager.boss_data.keys())

        if not monster_pool or not boss_pool:
            logger.error("秘境生成失败：怪物池或Boss池为空，请检查 monsters.json 和 bosses.json。")
            return None

        floor_events: List[FloorEvent] = []

        for _ in range(total_floors - 1):
            if random.random() < config["REALM_RULES"]["REALM_MONSTER_CHANCE"]:
                monster_id = random.choice(monster_pool)
                floor_events.append(FloorEvent(type="monster", data={"id": monster_id}))
            else:
                gold_reward = random.randint(50, 150) * (1 + level_index)
                floor_events.append(FloorEvent(type="treasure", data={"rewards": {"gold": int(gold_reward)}}))

        final_boss_id = random.choice(boss_pool)
        floor_events.append(FloorEvent(type="boss", data={"id": final_boss_id}))

        realm_id = f"dynamic_{player.level_index}_{int(time.time())}"

        return RealmInstance(
            id=realm_id,
            total_floors=total_floors,
            floors=floor_events
        )

class RealmManager:
    def __init__(self, db: DataBase, config: AstrBotConfig, config_manager: ConfigManager):
        self.db = db
        self.config = config
        self.config_manager = config_manager
        self.battle_logic = BattleManager(db, config, config_manager)

    async def start_session(self, player: Player, cmd_realm_advance: str) -> Tuple[bool, str, Player]:
        p = player.clone()
        if p.realm_id is not None:
             current_realm_instance = p.get_realm_instance()
             current_realm_name = f"{p.get_level(self.config_manager)}修士的试炼" if current_realm_instance else "未知的秘境"
             return False, f"你已身在【{current_realm_name}】之中，无法分心他顾。", p

        cost = 50 + (p.level_index * 25)

        if p.gold < cost:
            return False, f"本次历练需要 {cost} 灵石作为盘缠，你的灵石不足。", p

        realm_instance = RealmGenerator.generate_for_player(p, self.config, self.config_manager)
        if not realm_instance:
             return False, "天机混乱，秘境生成失败，请稍后再试。", p

        p.gold -= cost
        p.realm_id = realm_instance.id
        p.realm_floor = 0
        p.set_realm_instance(realm_instance)
        p.state = "探索中"
        p.state_start_time = time.time()

        realm_name = f"{p.get_level(self.config_manager)}修士的试炼"

        msg = (f"你消耗了 {cost} 灵石，开启了一场与你修为匹配的试炼。\n"
               f"你进入了【{realm_name}】，此地共有 {realm_instance.total_floors} 层。\n"
               f"使用「{cmd_realm_advance}」指令向前探索。")
        return True, msg, p

    async def advance_session(self, player: Player) -> Tuple[bool, str, Player, Dict[str, int]]:
        p = player.clone()
        realm_instance = p.get_realm_instance()

        if not p.realm_id or not realm_instance:
            return False, "你不在任何秘境中。", p, {}

        p.realm_floor += 1
        current_floor_index = p.realm_floor - 1

        if not (0 <= current_floor_index < len(realm_instance.floors)):
            p.realm_id = None
            p.realm_floor = 0
            p.set_realm_instance(None)
            p.state = "空闲"
            p.state_start_time = 0.0
            return False, "秘境探索数据异常，已将你传送出来。", p, {}

        event = realm_instance.floors[current_floor_index]
        event_log = [f"--- 第 {p.realm_floor}/{realm_instance.total_floors} 层 ---"]

        gained_items = {}
        victory = True
        
        if event.type == "monster" or event.type == "boss":
            victory, log, p_after_combat, gained_items = await self._handle_monster_event(p, event, p.level_index)
            p = p_after_combat
            event_log.extend(log)
            if not victory:
                p.realm_id = None
                p.realm_floor = 0
                p.set_realm_instance(None)
                p.state = "空闲"
                p.state_start_time = 0.0
        elif event.type == "treasure":
            log, p_after_event, gained_items = self._handle_treasure_event(p, event)
            p = p_after_event
            event_log.extend(log)
        else:
            event_log.append("此地异常安静，你谨慎地探索着，未发生任何事。")

        if victory and p.realm_id is not None and p.realm_floor >= realm_instance.total_floors:
            realm_name = f"{p.get_level(self.config_manager)}修士的试炼"
            event_log.append(f"\n你成功探索完了【{realm_name}】的所有区域！")
            p.realm_id = None
            p.realm_floor = 0
            p.set_realm_instance(None)
            p.state = "空闲"
            p.state_start_time = 0.0
            
        return victory, "\n".join(event_log), p, gained_items

    async def _handle_monster_event(self, p: Player, event: FloorEvent, player_level_index: int) -> Tuple[bool, List[str], Player, Dict[str, int]]:
        monster_template_id = event.data["id"]
        
        if event.type == "boss":
            scaling_factor = self.config["REALM_RULES"].get("REALM_BOSS_SCALING_FACTOR", 1.0)
            enemy = MonsterGenerator.create_boss(monster_template_id, player_level_index, self.config_manager, scaling_factor=scaling_factor)
        else:
            enemy = MonsterGenerator.create_monster(monster_template_id, player_level_index, self.config_manager)

        if not enemy:
            return False, ["怪物生成失败！"], p, {}

        victory, combat_log, p_after_combat = self.battle_logic.player_vs_monster(p, enemy)

        p = p_after_combat
        gained_items = {}
        if victory:
            rewards = enemy.rewards
            p.gold += int(rewards.get('gold', 0))
            p.experience += int(rewards.get('experience', 0))
            gained_items = rewards.get('items', {})

            if event.type == "boss":
                 combat_log.append(f"\n成功击败最终头目！")

        return victory, combat_log, p, gained_items

    def _handle_treasure_event(self, p: Player, event: FloorEvent) -> Tuple[List[str], Player, Dict[str, int]]:
        log = []
        gold_gained = event.data.get("rewards", {}).get("gold", 50)
        p.gold += int(gold_gained)
        log.append(f"你发现了一个宝箱，获得了 {int(gold_gained)} 灵石！")
        return log, p, {}