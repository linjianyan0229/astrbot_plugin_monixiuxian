# handlers/shop_handler.py
import random
from datetime import datetime
from typing import Optional, Tuple
from astrbot.api.event import AstrMessageEvent
from astrbot.api import AstrBotConfig
from ..data import DataBase
from ..config_manager import ConfigManager
from ..models import Player, PlayerEffect, Item
from .utils import player_required

CMD_BUY = "购买"
CMD_USE_ITEM = "使用"

__all__ = ["ShopHandler"]

def calculate_item_effect(item_info: Optional[Item], quantity: int) -> Tuple[Optional[PlayerEffect], str, float]:
    if not item_info or not (effect_config := item_info.effect):
        return None, f"【{item_info.name if item_info else '未知物品'}】似乎只是凡物，无法使用。", 0.0

    effect = PlayerEffect()
    messages = []

    # 新版effect格式：直接使用属性名作为key
    if "add_experience" in effect_config:
        value = effect_config["add_experience"] * quantity
        effect.experience = value
        messages.append(f"修为+{value}")
    
    if "add_gold" in effect_config:
        value = effect_config["add_gold"] * quantity
        effect.gold = value
        messages.append(f"灵石+{value}")
    
    if "add_hp" in effect_config:
        value = effect_config["add_hp"] * quantity
        effect.hp = value
        messages.append(f"气血+{value}")
    
    if "add_max_hp" in effect_config:
        value = effect_config["add_max_hp"] * quantity
        effect.max_hp = value
        messages.append(f"气血上限+{value}")
    
    if "add_spiritual_power" in effect_config:
        value = effect_config["add_spiritual_power"] * quantity
        effect.spiritual_power = value
        messages.append(f"灵力+{value}")
    
    if "add_mental_power" in effect_config:
        value = effect_config["add_mental_power"] * quantity
        effect.mental_power = value
        messages.append(f"精神力+{value}")
    
    if "add_attack" in effect_config:
        value = effect_config["add_attack"] * quantity
        effect.attack = value
        messages.append(f"攻击+{value}")
    
    if "add_defense" in effect_config:
        value = effect_config["add_defense"] * quantity
        effect.defense = value
        messages.append(f"防御+{value}")
    
    # 突破成功率加成（buff效果，不叠加数量）
    breakthrough_bonus = 0.0
    if "add_breakthrough_bonus" in effect_config:
        breakthrough_bonus = effect_config["add_breakthrough_bonus"]
        bonus_percent = int(breakthrough_bonus * 100)
        messages.append(f"💫突破成功率+{bonus_percent}%")

    if not messages:
        return None, f"你研究了半天，也没能参透【{item_info.name}】的用法。", 0.0

    full_message = f"✨ 你使用了 {quantity} 个【{item_info.name}】\n" + "、".join(messages) + "！"
    
    # 如果有突破加成，添加提示
    if breakthrough_bonus > 0:
        full_message += f"\n💡 提示：突破加成buff已激活，下次突破时生效！"
    
    return effect, full_message, breakthrough_bonus

class ShopHandler:
    # 坊市相关指令处理器
    
    def __init__(self, db: DataBase, config_manager: ConfigManager, config: AstrBotConfig):
        self.db = db
        self.config_manager = config_manager
        self.config = config

    def _generate_stock_for_item(self, item_price: int, rng: random.Random) -> int:
        """根据物品价格生成库存数量，价格越贵库存越少"""
        if item_price <= 500:
            return rng.randint(15, 25)
        elif item_price <= 2000:
            return rng.randint(8, 15)
        elif item_price <= 10000:
            return rng.randint(3, 8)
        elif item_price <= 100000:
            return rng.randint(2, 5)
        else:
            return rng.randint(1, 3)

    async def handle_shop(self, event: AstrMessageEvent):
        today_date = datetime.now().strftime('%Y%m%d')
        reply_msg = f"--- 仙途坊市 ({datetime.now().strftime('%Y-%m-%d')}) ---\n"
        
        # 获取所有可售卖的商品
        all_sellable_items = [item for item in self.config_manager.item_data.values() if item.price > 0]
        
        # 从配置中获取每日商品数量
        item_count = self.config["VALUES"].get("SHOP_DAILY_ITEM_COUNT", 8)

        if not all_sellable_items:
            reply_msg += "今日坊市暂无商品。\n"
        else:
            # 使用当天日期作为随机种子，确保每日商品固定
            today_seed = int(today_date)
            rng = random.Random(today_seed)
            
            # 如果商品总数小于等于设定数量，则全部显示
            if len(all_sellable_items) <= item_count:
                daily_items = all_sellable_items
            else:
                daily_items = rng.sample(all_sellable_items, item_count)
            
            # 检查今日库存是否已初始化
            existing_inventory = await self.db.get_shop_inventory(today_date)
            if not existing_inventory:
                # 初始化今日库存
                inventory_dict = {}
                for item in daily_items:
                    stock = self._generate_stock_for_item(item.price, rng)
                    inventory_dict[item.id] = stock
                await self.db.init_shop_inventory(today_date, inventory_dict)
                existing_inventory = inventory_dict
            
            sorted_items = sorted(daily_items, key=lambda item: item.price)

            for info in sorted_items:
                stock = existing_inventory.get(info.id, 0)
                stock_display = f"(库存: {stock})" if stock > 0 else "(已售罄)"
                reply_msg += f"【{info.name}】售价：{info.price} 灵石 {stock_display}\n"
        
        reply_msg += "------------------\n"
        reply_msg += f"使用「{CMD_BUY} <物品名> [数量]」进行购买。"
        yield event.plain_result(reply_msg)

    @player_required
    async def handle_backpack(self, player: Player, event: AstrMessageEvent):
        inventory = await self.db.get_inventory_by_user_id(player.user_id, self.config_manager)
        if not inventory:
            yield event.plain_result("道友的背包空空如也。")
            return

        reply_msg = f"--- {event.get_sender_name()} 的背包 ---\n"
        for item in inventory:
            reply_msg += f"【{item['name']}】x{item['quantity']} - {item['description']}\n"
        reply_msg += "--------------------------"
        yield event.plain_result(reply_msg)

    @player_required
    async def handle_buy(self, player: Player, event: AstrMessageEvent, item_name: str, quantity: int):
        if not item_name or quantity <= 0:
            yield event.plain_result(f"指令格式错误。正确用法: `{CMD_BUY} <物品名> [数量]`。")
            return

        item_to_buy = self.config_manager.get_item_by_name(item_name)
        if not item_to_buy or item_to_buy[1].price <= 0:
            yield event.plain_result(f"道友，小店中并无「{item_name}」这件商品。")
            return

        item_id_to_add, target_item_info = item_to_buy
        today_date = datetime.now().strftime('%Y%m%d')
        
        # 检查今日商店库存
        current_stock = await self.db.get_shop_stock(today_date, item_id_to_add)
        
        if current_stock is None:
            yield event.plain_result(f"「{item_name}」今日未在坊市上架，请明日再来。")
            return
        
        if current_stock < quantity:
            if current_stock > 0:
                yield event.plain_result(f"库存不足！「{item_name}」今日仅剩 {current_stock} 件，无法购买 {quantity} 件。")
            else:
                yield event.plain_result(f"「{item_name}」今日已售罄，请明日再来。")
            return
        
        total_cost = target_item_info.price * quantity

        # 先尝试购买（扣除灵石并添加到背包）
        success, reason = await self.db.transactional_buy_item(player.user_id, item_id_to_add, quantity, total_cost)

        if success:
            # 购买成功后扣减库存
            stock_decreased = await self.db.decrease_shop_stock(today_date, item_id_to_add, quantity)
            if not stock_decreased:
                # 理论上不会发生，因为我们已经检查过库存
                logger.error(f"购买成功但库存扣减失败: user={player.user_id}, item={item_id_to_add}, qty={quantity}")
            
            updated_player = await self.db.get_player_by_id(player.user_id)
            remaining_stock = current_stock - quantity
            if updated_player:
                yield event.plain_result(f"购买成功！花费{total_cost}灵石，购得「{item_name}」x{quantity}。剩余灵石 {updated_player.gold}。\n坊市剩余「{item_name}」库存: {remaining_stock}")
            else:
                yield event.plain_result(f"购买成功！花费{total_cost}灵石，购得「{item_name}」x{quantity}。\n坊市剩余「{item_name}」库存: {remaining_stock}")
        else:
            if reason == "ERROR_INSUFFICIENT_FUNDS":
                yield event.plain_result(f"灵石不足！购买 {quantity}个「{item_name}」需{total_cost}灵石，你只有{player.gold}。")
            else:
                yield event.plain_result("购买失败，坊市交易繁忙，请稍后再试。")

    @player_required
    async def handle_use(self, player: Player, event: AstrMessageEvent, item_name: str, quantity: int = 1):
        if not item_name or quantity <= 0:
            yield event.plain_result(f"指令格式错误。正确用法: `{CMD_USE_ITEM} <物品名> [数量]`。")
            return

        item_to_use = self.config_manager.get_item_by_name(item_name)
        if not item_to_use:
            yield event.plain_result(f"背包中似乎没有名为「{item_name}」的物品。")
            return
        
        target_item_id, target_item_info = item_to_use
        
        # 检查背包数量
        inventory_item = await self.db.get_item_from_inventory(player.user_id, target_item_id)
        if not inventory_item or inventory_item['quantity'] < quantity:
            yield event.plain_result(f"使用失败！你的「{item_name}」数量不足 {quantity} 个。")
            return

        # 根据物品类型执行不同功能
        if target_item_info.type == "法器":
            # 执行装备逻辑
            if quantity > 1:
                yield event.plain_result(f"每次只能装备一件法器。")
                return

            p_clone = player.clone()
            unequipped_item_id = None
            slot_name = target_item_info.subtype

            if slot_name == "武器":
                if p_clone.equipped_weapon: unequipped_item_id = p_clone.equipped_weapon
                p_clone.equipped_weapon = target_item_id
            elif slot_name == "防具":
                if p_clone.equipped_armor: unequipped_item_id = p_clone.equipped_armor
                p_clone.equipped_armor = target_item_id
            elif slot_name == "饰品":
                if p_clone.equipped_accessory: unequipped_item_id = p_clone.equipped_accessory
                p_clone.equipped_accessory = target_item_id
            else:
                yield event.plain_result(f"「{item_name}」似乎不是一件可穿戴的法器。")
                return

            # 更新数据库
            await self.db.remove_item_from_inventory(player.user_id, target_item_id, 1)
            if unequipped_item_id:
                await self.db.add_items_to_inventory_in_transaction(player.user_id, {unequipped_item_id: 1})
            
            await self.db.update_player(p_clone)
            yield event.plain_result(f"已成功装备【{item_name}】。")

        else:
            # 消耗品
            effect, msg, breakthrough_bonus = calculate_item_effect(target_item_info, quantity)
            if not effect:
                yield event.plain_result(msg)
                return

            success = await self.db.transactional_apply_item_effect(player.user_id, target_item_id, quantity, effect, breakthrough_bonus)

            if success:
                yield event.plain_result(msg)
            else:
                # 理论上这里的数量不足检查不会触发，但作为保险
                yield event.plain_result(f"使用失败！可能发生了未知错误。")