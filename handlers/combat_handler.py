# handlers/combat_handler.py
from astrbot.api.event import AstrMessageEvent
from astrbot.api import AstrBotConfig
from astrbot.core.message.components import At
from ..data import DataBase
from ..core import BattleManager
from ..config_manager import ConfigManager
from ..models import Player
from .utils import player_required

CMD_SPAR = "切磋"
CMD_FIGHT_BOSS = "讨伐boss"

__all__ = ["CombatHandler"]

class CombatHandler:
    # 战斗相关指令处理器
    
    def __init__(self, db: DataBase, config: AstrBotConfig, config_manager: ConfigManager):
        self.db = db
        self.config = config
        self.config_manager = config_manager
        self.battle_manager = BattleManager(db, config, config_manager)

    @player_required
    async def handle_spar(self, attacker: Player, event: AstrMessageEvent):
        if attacker.hp < attacker.max_hp:
            yield event.plain_result("你当前气血不满，无法与人切磋，请先恢复。")
            return

        message_obj = event.message_obj
        mentioned_user_id = None
        defender_name = None

        if hasattr(message_obj, "message"):
            for comp in message_obj.message:
                if isinstance(comp, At):
                    mentioned_user_id = comp.qq
                    if hasattr(comp, 'name'):
                        defender_name = comp.name
                    break

        if not mentioned_user_id:
            yield event.plain_result(f"请指定切磋对象，例如：`{CMD_SPAR} @张三`")
            return

        if str(mentioned_user_id) == attacker.user_id:
            yield event.plain_result("道友，不可与自己为敌。")
            return

        defender = await self.db.get_player_by_id(str(mentioned_user_id))
        if not defender:
            yield event.plain_result("对方尚未踏入仙途，无法应战。")
            return

        if defender.hp < defender.max_hp:
            yield event.plain_result("对方气血不满，此时挑战非君子所为。")
            return

        attacker_name = event.get_sender_name()

        _, _, report_lines = self.battle_manager.player_vs_player(attacker, defender, attacker_name, defender_name)
        yield event.plain_result("\n".join(report_lines))

    async def handle_boss_list(self, event: AstrMessageEvent):
        import time
        active_bosses_with_templates = await self.battle_manager.ensure_bosses_are_spawned()
        
        # 获取所有Boss的冷却信息
        all_boss_cooldowns = await self.db.get_all_boss_cooldowns()
        current_time = time.time()
        
        # 获取所有Boss模板，包括冷却中的
        all_boss_templates = self.config_manager.boss_data
        cooldown_bosses = []
        for boss_id, cooldown_info in all_boss_cooldowns.items():
            if cooldown_info['respawn_at'] > current_time:
                # 这个Boss在冷却中
                template_config = all_boss_templates.get(boss_id)
                if template_config:
                    cooldown_bosses.append((boss_id, cooldown_info, template_config))

        if not active_bosses_with_templates and not cooldown_bosses:
            yield event.plain_result("天地间一片祥和，暂无妖兽作乱。")
            return

        # 分类Boss
        alive_bosses = []
        dead_bosses = []
        
        for instance, template in active_bosses_with_templates:
            if instance.current_hp > 0:
                alive_bosses.append((instance, template))
            else:
                dead_bosses.append((instance, template))

        report = []

        # 可讨伐Boss列表
        if alive_bosses:
            report.append("🔥 可讨伐的世界Boss 🔥")
            report.append("=" * 30)
            
            # 按标签类型分组Boss
            grouped_bosses = self._group_bosses_by_tags(alive_bosses)
            
            for group_name, bosses in grouped_bosses.items():
                if bosses:
                    report.append(f"\n📋 {group_name}")
                    report.append("-" * 20)
                    
                    for instance, template in bosses:
                        # 获取Boss的境界名称
                        boss_level_name = instance.get_level_name(self.config_manager)
                        
                        # 从配置中获取原始标签信息
                        boss_config = self.config_manager.boss_data.get(instance.boss_id, {})
                        boss_tags = boss_config.get('tags', [])
                        
                        # 构建标签显示
                        tags_display = self._format_boss_tags(boss_tags)
                        
                        # 构建Boss名称显示（包含标签前缀）
                        boss_name_display = self._format_boss_name(boss_tags, boss_config.get('name', template.name))
                        
                        report.append(
                            f"【{boss_name_display}】 (ID: {instance.boss_id})\n"
                            f"  境界: {boss_level_name}\n"
                            f"  {tags_display}\n"
                            f"  ❤️剩余生命: {instance.current_hp}/{instance.max_hp}"
                        )
                        participants = await self.db.get_boss_participants(instance.boss_id)
                        if participants:
                            report.append("  - 伤害贡献榜 -")
                            for p_data in participants[:3]:
                                report.append(f"    - {p_data['user_name']}: {p_data['total_damage']} 伤害")
                        report.append("")  # 添加空行分隔

        # 已死亡Boss列表
        if dead_bosses:
            report.append("💀 已被击败的世界Boss 💀")
            report.append("=" * 30)
            for instance, template in dead_bosses:
                # 获取Boss的境界名称
                boss_level_name = instance.get_level_name(self.config_manager)
                
                # 从配置中获取原始标签信息
                boss_config = self.config_manager.boss_data.get(instance.boss_id, {})
                boss_tags = boss_config.get('tags', [])
                
                # 构建标签显示
                tags_display = self._format_boss_tags(boss_tags)
                
                # 构建Boss名称显示（包含标签前缀）
                boss_name_display = self._format_boss_name(boss_tags, boss_config.get('name', template.name))
                
                report.append(
                    f"【{boss_name_display}】 (ID: {instance.boss_id})\n"
                    f"  境界: {boss_level_name}\n"
                    f"  {tags_display}\n"
                    f"  ❤️剩余生命: {instance.current_hp}/{instance.max_hp}"
                )
                participants = await self.db.get_boss_participants(instance.boss_id)
                if participants:
                    report.append("  - 伤害贡献榜 -")
                    for p_data in participants[:3]:
                        report.append(f"    - {p_data['user_name']}: {p_data['total_damage']} 伤害")
                report.append("")  # 添加空行分隔

        if not alive_bosses:
            report.append("🔥 可讨伐的世界Boss 🔥")
            report.append("=" * 30)
            report.append("暂无可讨伐的Boss")
            report.append("")  # 添加空行分隔

        if not dead_bosses:
            report.append("💀 已被击败的世界Boss 💀")
            report.append("=" * 30)
            report.append("暂无被击败的Boss")
            report.append("")  # 添加空行分隔

        # 冷却中的Boss列表
        if cooldown_bosses:
            report.append("⏳ 冷却重生中的世界Boss ⏳")
            report.append("=" * 30)
            for boss_id, cooldown_info, template_config in cooldown_bosses:
                remaining_time = cooldown_info['respawn_at'] - current_time
                remaining_hours = int(remaining_time / 3600)
                remaining_minutes = int((remaining_time % 3600) / 60)
                
                boss_name = template_config.get('name', 'Unknown')
                boss_tags = template_config.get('tags', [])
                tags_display = self._format_boss_tags(boss_tags)
                boss_name_display = self._format_boss_name(boss_tags, boss_name)
                
                time_display = f"{remaining_hours}小时{remaining_minutes}分钟" if remaining_hours > 0 else f"{remaining_minutes}分钟"
                
                report.append(
                    f"【{boss_name_display}】 (ID: {boss_id})\n"
                    f"  {tags_display}\n"
                    f"  ⏳重生倒计时: {time_display}"
                )
                report.append("")  # 添加空行分隔

        report.append(f"使用「{CMD_FIGHT_BOSS} <Boss ID>」发起挑战！")

        yield event.plain_result("\n".join(report).strip())

    @player_required
    async def handle_fight_boss(self, player: Player, event: AstrMessageEvent, boss_id: str):
        if not boss_id:
            yield event.plain_result(f"指令格式错误！请使用「{CMD_FIGHT_BOSS} <Boss ID>」。")
            return

        player_name = event.get_sender_name()
        result_msg = await self.battle_manager.player_fight_boss(player, boss_id, player_name)
        yield event.plain_result(result_msg)

    def _format_boss_tags(self, tags: list) -> str:
        """格式化Boss标签显示"""
        if not tags:
            return "🏷️ 标签: 无"
        
        # 标签图标映射
        tag_icons = {
            "野兽": "🐺",
            "迅捷": "⚡", 
            "剧毒": "☠️",
            "精英": "⭐",
            "领主": "👑",
            "魔族": "👹",
            "鬼魅": "👻",
            "元素·火": "🔥",
            "不死": "💀",
            "机械": "⚙️",
            "元素·冰": "❄️",
            "元素·雷": "⚡",
            "元素·土": "🪨",
            "元素·风": "💨",
            "妖精": "🧚",
            "混沌": "🌀"
        }
        
        # 构建标签显示
        tag_display = []
        for tag in tags:
            icon = tag_icons.get(tag, "🏷️")
            tag_display.append(f"{icon}{tag}")
        
        return f"🏷️ 标签: {' '.join(tag_display)}"

    def _format_boss_name(self, tags: list, base_name: str) -> str:
        """格式化Boss名称显示（包含标签前缀）"""
        if not tags:
            return base_name
        
        # 获取标签前缀
        prefixes = []
        for tag in tags:
            tag_config = self.config_manager.tag_data.get(tag, {})
            prefix = tag_config.get('name_prefix', '')
            if prefix and prefix not in prefixes:
                prefixes.append(prefix)
        
        # 组合前缀和名称
        if prefixes:
            return f"{''.join(prefixes)}{base_name}"
        return base_name

    def _group_bosses_by_tags(self, bosses: list) -> dict:
        """按标签类型分组Boss"""
        groups = {
            "👑 领主级Boss": [],
            "⭐ 精英级Boss": [],
            "🔥 元素系Boss": [],
            "👹 魔族Boss": [],
            "💀 不死系Boss": [],
            "🐺 野兽系Boss": [],
            "⚙️ 机械系Boss": [],
            "🧚 妖精系Boss": [],
            "🌀 混沌系Boss": [],
            "其他Boss": []
        }
        
        for instance, template in bosses:
            # 从配置中获取原始标签信息
            boss_config = self.config_manager.boss_data.get(instance.boss_id, {})
            tags = boss_config.get('tags', [])
            categorized = False
            
            # 按优先级分类
            if "领主" in tags:
                groups["👑 领主级Boss"].append((instance, template))
                categorized = True
            elif "精英" in tags:
                groups["⭐ 精英级Boss"].append((instance, template))
                categorized = True
            elif any(tag.startswith("元素·") for tag in tags):
                groups["🔥 元素系Boss"].append((instance, template))
                categorized = True
            elif "魔族" in tags:
                groups["👹 魔族Boss"].append((instance, template))
                categorized = True
            elif "不死" in tags:
                groups["💀 不死系Boss"].append((instance, template))
                categorized = True
            elif "野兽" in tags:
                groups["🐺 野兽系Boss"].append((instance, template))
                categorized = True
            elif "机械" in tags:
                groups["⚙️ 机械系Boss"].append((instance, template))
                categorized = True
            elif "妖精" in tags:
                groups["🧚 妖精系Boss"].append((instance, template))
                categorized = True
            elif "混沌" in tags:
                groups["🌀 混沌系Boss"].append((instance, template))
                categorized = True
            
            if not categorized:
                groups["其他Boss"].append((instance, template))
        
        # 移除空分组
        return {k: v for k, v in groups.items() if v}