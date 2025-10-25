# handlers/bank_handler.py
import time
from astrbot.api.event import AstrMessageEvent
from astrbot.api import AstrBotConfig
from astrbot.core.message.components import At
from ..data import DataBase
from ..models import Player
from .utils import player_required

CMD_BANK_FIXED_DEPOSIT = "定期存款"
CMD_BANK_CURRENT_DEPOSIT = "活期存款"
CMD_BANK_WITHDRAW = "取款"
CMD_BANK_INFO = "钱庄"
CMD_TRANSFER = "转账"

__all__ = ["BankHandler"]

class BankHandler:
    """钱庄相关指令处理器"""
    
    def __init__(self, db: DataBase, config: AstrBotConfig):
        self.db = db
        self.config = config

    @player_required
    async def handle_bank_info(self, player: Player, event: AstrMessageEvent):
        """查看钱庄信息"""
        current_time = time.time()
        
        # 优先显示道号，没有则显示QQ名称
        display_name = player.dao_name if player.dao_name else event.get_sender_name()
        
        # 获取定期存款
        fixed_deposits = await self.db.get_fixed_deposits(player.user_id)
        
        # 获取活期存款
        current_deposit = await self.db.get_current_deposit(player.user_id)
        
        msg = ["💰 仙途钱庄 💰", "━━━━━━━━━━━━━━━"]
        msg.append(f"👤 道友：{display_name}")
        msg.append(f"💵 随身灵石：{player.gold}")
        msg.append("")
        
        # 定期存款信息
        if fixed_deposits:
            msg.append("📊 定期存款：")
            for deposit in fixed_deposits:
                hours_passed = (current_time - deposit['deposit_time']) / 3600
                hours_total = deposit['duration_hours']
                is_mature = current_time >= deposit['mature_time']
                
                rate_per_hour = self.config["VALUES"]["BANK_FIXED_RATE_PER_HOUR"]
                current_value = int(deposit['amount'] * (rate_per_hour ** hours_passed))
                mature_value = int(deposit['amount'] * (rate_per_hour ** hours_total))
                
                status = "✅ 已到期" if is_mature else f"⏳ 进行中"
                remaining = "" if is_mature else f"（剩余 {int((deposit['mature_time'] - current_time) / 3600)} 小时）"
                
                msg.append(f"  [ID: {deposit['id']}] {status}{remaining}")
                msg.append(f"  - 本金：{deposit['amount']} 灵石")
                msg.append(f"  - 期限：{hours_total} 小时")
                msg.append(f"  - 当前价值：{current_value} 灵石")
                msg.append(f"  - 到期可得：{mature_value} 灵石")
                msg.append("")
        else:
            msg.append("📊 定期存款：无")
            msg.append("")
        
        # 活期存款信息
        if current_deposit:
            hours_passed = (current_time - current_deposit['deposit_time']) / 3600
            min_hours = self.config["VALUES"]["BANK_CURRENT_MIN_HOURS"]
            rate_per_hour = self.config["VALUES"]["BANK_CURRENT_RATE_PER_HOUR"]
            
            can_withdraw = hours_passed >= min_hours
            current_value = int(current_deposit['amount'] * (rate_per_hour ** hours_passed))
            
            status = "✅ 可取出" if can_withdraw else f"⏳ 需等待 {int(min_hours - hours_passed)} 小时"
            
            msg.append("💳 活期存款：")
            msg.append(f"  状态：{status}")
            msg.append(f"  本金：{current_deposit['amount']} 灵石")
            msg.append(f"  当前价值：{current_value} 灵石")
            msg.append(f"  已存时长：{int(hours_passed)} 小时")
        else:
            msg.append("💳 活期存款：无")
        
        msg.append("")
        msg.append("━━━━━━━━━━━━━━━")
        msg.append("💡 指令说明：")
        msg.append(f"  「{CMD_BANK_FIXED_DEPOSIT} [金额] [小时]」- 定期存款")
        msg.append(f"  「{CMD_BANK_CURRENT_DEPOSIT} [金额]」- 活期存款")
        msg.append(f"  「{CMD_BANK_WITHDRAW} 定期」- 取出所有到期定期")
        msg.append(f"  「{CMD_BANK_WITHDRAW} 活期 [金额]」- 取出指定金额")
        msg.append(f"  「{CMD_TRANSFER} [金额] @道友」- 转账")
        
        yield event.plain_result("\n".join(msg))

    @player_required
    async def handle_fixed_deposit(self, player: Player, event: AstrMessageEvent, amount: int, hours: int):
        """定期存款"""
        # 检查是否提供了参数
        if amount <= 0 or hours <= 0:
            min_hours = self.config["VALUES"]["BANK_FIXED_MIN_HOURS"]
            rate_per_hour = self.config["VALUES"]["BANK_FIXED_RATE_PER_HOUR"]
            rate_percent = (rate_per_hour - 1) * 100
            
            msg = [
                "💰 定期存款指南",
                "━━━━━━━━━━━━━━━",
                "🔹 使用方法：",
                f"  {CMD_BANK_FIXED_DEPOSIT} <金额> <时长>",
                "",
                "🔹 示例：",
                f"  {CMD_BANK_FIXED_DEPOSIT} 10000 24",
                f"  {CMD_BANK_FIXED_DEPOSIT} 50000 48",
                "",
                "🔹 规则说明：",
                f"  • 最低存期：{min_hours} 小时",
                f"  • 每小时利率：{rate_percent:.1f}%",
                f"  • 到期后可通过「{CMD_BANK_WITHDRAW} 定期」取出",
                "  • 利息按复利计算",
                "  • 未到期不可提前取出",
                "━━━━━━━━━━━━━━━"
            ]
            yield event.plain_result("\n".join(msg))
            return
        
        min_hours = self.config["VALUES"]["BANK_FIXED_MIN_HOURS"]
        if hours < min_hours:
            yield event.plain_result(f"定期存款最少需要 {min_hours} 小时！")
            return
        
        if player.gold < amount:
            yield event.plain_result(f"灵石不足！你当前拥有 {player.gold} 灵石。")
            return
        
        # 扣除灵石
        player.gold -= amount
        await self.db.update_player(player)
        
        # 创建定期存款
        current_time = time.time()
        mature_time = current_time + hours * 3600
        deposit_id = await self.db.create_fixed_deposit(
            player.user_id, amount, hours, current_time, mature_time
        )
        
        # 计算到期收益
        rate_per_hour = self.config["VALUES"]["BANK_FIXED_RATE_PER_HOUR"]
        mature_value = int(amount * (rate_per_hour ** hours))
        profit = mature_value - amount
        
        msg = [
            "✅ 定期存款成功！",
            "━━━━━━━━━━━━━━━",
            f"存款编号：{deposit_id}",
            f"本金：{amount} 灵石",
            f"期限：{hours} 小时",
            f"到期可得：{mature_value} 灵石",
            f"预计收益：+{profit} 灵石",
            "━━━━━━━━━━━━━━━",
            f"💰 剩余灵石：{player.gold}"
        ]
        yield event.plain_result("\n".join(msg))

    @player_required
    async def handle_current_deposit(self, player: Player, event: AstrMessageEvent, amount: int):
        """活期存款"""
        # 检查是否提供了参数
        if amount <= 0:
            min_hours = self.config["VALUES"]["BANK_CURRENT_MIN_HOURS"]
            rate_per_hour = self.config["VALUES"]["BANK_CURRENT_RATE_PER_HOUR"]
            rate_percent = (rate_per_hour - 1) * 100
            
            msg = [
                "💳 活期存款指南",
                "━━━━━━━━━━━━━━━",
                "🔹 使用方法：",
                f"  {CMD_BANK_CURRENT_DEPOSIT} <金额>",
                "",
                "🔹 示例：",
                f"  {CMD_BANK_CURRENT_DEPOSIT} 10000",
                f"  {CMD_BANK_CURRENT_DEPOSIT} 50000",
                "",
                "🔹 规则说明：",
                f"  • 最低存期：{min_hours} 小时",
                f"  • 每小时利率：{rate_percent:.1f}%",
                f"  • 满{min_hours}小时后可随时取出",
                f"  • 通过「{CMD_BANK_WITHDRAW} 活期 <金额>」取出",
                "  • 可以部分取出，剩余部分重新计息",
                "  • 利息按复利计算",
                "━━━━━━━━━━━━━━━"
            ]
            yield event.plain_result("\n".join(msg))
            return
        
        if player.gold < amount:
            yield event.plain_result(f"灵石不足！你当前拥有 {player.gold} 灵石。")
            return
        
        # 扣除灵石
        player.gold -= amount
        await self.db.update_player(player)
        
        # 创建或更新活期存款
        current_time = time.time()
        await self.db.create_or_update_current_deposit(player.user_id, amount, current_time)
        
        min_hours = self.config["VALUES"]["BANK_CURRENT_MIN_HOURS"]
        
        msg = [
            "✅ 活期存款成功！",
            "━━━━━━━━━━━━━━━",
            f"存入金额：{amount} 灵石",
            f"最低存期：{min_hours} 小时",
            "存期结束后可随时取出本金和利息",
            "━━━━━━━━━━━━━━━",
            f"💰 剩余灵石：{player.gold}"
        ]
        yield event.plain_result("\n".join(msg))

    async def handle_withdraw_usage(self, event: AstrMessageEvent):
        """显示取款用法"""
        msg = [
            "🏦 取款指令指南",
            "━━━━━━━━━━━━━━━",
            "🔹 定期存款取款：",
            f"  {CMD_BANK_WITHDRAW} 定期",
            "  • 一次性取出所有已到期的定期存款",
            "  • 未到期的存款不会被取出",
            "",
            "🔹 活期存款取款：",
            f"  {CMD_BANK_WITHDRAW} 活期 <金额>",
            "  • 取出指定金额的活期存款",
            "  • 可以部分取出",
            "",
            "🔹 示例：",
            f"  {CMD_BANK_WITHDRAW} 定期",
            f"  {CMD_BANK_WITHDRAW} 活期 10000",
            f"  {CMD_BANK_WITHDRAW} 活期 50000",
            "━━━━━━━━━━━━━━━"
        ]
        yield event.plain_result("\n".join(msg))

    @player_required
    async def handle_withdraw_fixed(self, player: Player, event: AstrMessageEvent):
        """取出所有到期的定期存款"""
        deposits = await self.db.get_fixed_deposits(player.user_id)
        
        if not deposits:
            yield event.plain_result("你没有任何定期存款！")
            return
        
        current_time = time.time()
        rate_per_hour = self.config["VALUES"]["BANK_FIXED_RATE_PER_HOUR"]
        
        # 筛选到期的存款
        mature_deposits = [d for d in deposits if current_time >= d['mature_time']]
        
        if not mature_deposits:
            yield event.plain_result("你没有到期的定期存款！请耐心等待到期后再取出。")
            return
        
        # 计算总金额
        total_principal = 0
        total_profit = 0
        total_amount = 0
        
        for deposit in mature_deposits:
            hours_total = deposit['duration_hours']
            final_amount = int(deposit['amount'] * (rate_per_hour ** hours_total))
            profit = final_amount - deposit['amount']
            
            total_principal += deposit['amount']
            total_profit += profit
            total_amount += final_amount
            
            # 删除存款记录
            await self.db.delete_fixed_deposit(deposit['id'])
        
        # 返还灵石
        player.gold += total_amount
        await self.db.update_player(player)
        
        msg = [
            "✅ 定期存款取出成功！",
            "━━━━━━━━━━━━━━━",
            f"取出笔数：{len(mature_deposits)} 笔",
            f"总本金：{total_principal} 灵石",
            f"总利息：+{total_profit} 灵石",
            f"总到账：{total_amount} 灵石",
            "━━━━━━━━━━━━━━━",
            f"💰 当前灵石：{player.gold}"
        ]
        yield event.plain_result("\n".join(msg))

    @player_required
    async def handle_withdraw_current(self, player: Player, event: AstrMessageEvent, amount: int):
        """取出指定金额的活期存款"""
        if amount <= 0:
            yield event.plain_result("取款金额必须大于0！")
            return
        
        deposit = await self.db.get_current_deposit(player.user_id)
        
        if not deposit:
            yield event.plain_result("你没有活期存款！")
            return
        
        current_time = time.time()
        hours_passed = (current_time - deposit['deposit_time']) / 3600
        min_hours = self.config["VALUES"]["BANK_CURRENT_MIN_HOURS"]
        
        if hours_passed < min_hours:
            remaining = int(min_hours - hours_passed)
            yield event.plain_result(f"活期存款需要至少存 {min_hours} 小时！还需等待 {remaining} 小时。")
            return
        
        # 计算当前总价值（本金+利息）
        rate_per_hour = self.config["VALUES"]["BANK_CURRENT_RATE_PER_HOUR"]
        current_total_value = int(deposit['amount'] * (rate_per_hour ** hours_passed))
        
        if amount > current_total_value:
            yield event.plain_result(f"取款金额超过活期存款总价值！你的活期存款当前价值为 {current_total_value} 灵石。")
            return
        
        # 返还灵石
        player.gold += amount
        await self.db.update_player(player)
        
        # 计算剩余金额（按比例扣除本金）
        remaining_value = current_total_value - amount
        
        if remaining_value <= 0:
            # 全部取出，删除存款记录
            await self.db.delete_current_deposit(player.user_id)
            profit = current_total_value - deposit['amount']
            
            msg = [
                "✅ 活期存款全部取出！",
                "━━━━━━━━━━━━━━━",
                f"本金：{deposit['amount']} 灵石",
                f"利息：+{profit} 灵石",
                f"到账：{amount} 灵石",
                f"存期：{int(hours_passed)} 小时",
                "━━━━━━━━━━━━━━━",
                f"💰 当前灵石：{player.gold}"
            ]
        else:
            # 部分取出，按比例计算新的本金（忽略利息）
            remaining_principal = int(deposit['amount'] * (remaining_value / current_total_value))
            
            # 更新存款记录，重置存款时间
            await self.db.update_current_deposit_amount(player.user_id, remaining_principal, current_time)
            
            msg = [
                "✅ 活期存款部分取出！",
                "━━━━━━━━━━━━━━━",
                f"取出金额：{amount} 灵石",
                f"剩余本金：{remaining_principal} 灵石",
                f"（存期已重置，需重新计息）",
                "━━━━━━━━━━━━━━━",
                f"💰 当前灵石：{player.gold}"
            ]
        
        yield event.plain_result("\n".join(msg))

    @player_required
    async def handle_transfer(self, player: Player, event: AstrMessageEvent, amount: int):
        """转账"""
        # 检查是否提供了参数
        if amount <= 0:
            msg = [
                "💸 转账指令指南",
                "━━━━━━━━━━━━━━━",
                "🔹 使用方法：",
                f"  {CMD_TRANSFER} <金额> @道友",
                "",
                "🔹 示例：",
                f"  {CMD_TRANSFER} 1000 @张三",
                f"  {CMD_TRANSFER} 50000 @李四",
                "",
                "🔹 规则说明：",
                "  • 金额必须大于0",
                "  • 需要@对方才能转账",
                "  • 对方必须已踏入仙途",
                "  • 不能给自己转账",
                "  • 转账即时到账",
                "━━━━━━━━━━━━━━━"
            ]
            yield event.plain_result("\n".join(msg))
            return
        
        if player.gold < amount:
            yield event.plain_result(f"灵石不足！你当前拥有 {player.gold} 灵石。")
            return
        
        # 获取被@的用户
        message_obj = event.message_obj
        target_user_id = None
        target_name = None
        
        if hasattr(message_obj, "message"):
            for comp in message_obj.message:
                if isinstance(comp, At):
                    target_user_id = str(comp.qq)
                    if hasattr(comp, 'name'):
                        target_name = comp.name
                    break
        
        if not target_user_id:
            yield event.plain_result(f"请指定转账对象，例如：「{CMD_TRANSFER} 100 @张三」")
            return
        
        if target_user_id == player.user_id:
            yield event.plain_result("不能给自己转账！")
            return
        
        # 检查目标玩家是否存在
        target_player = await self.db.get_player_by_id(target_user_id)
        if not target_player:
            yield event.plain_result("对方尚未踏入仙途，无法接收转账。")
            return
        
        # 执行转账
        player.gold -= amount
        target_player.gold += amount
        
        await self.db.update_player(player)
        await self.db.update_player(target_player)
        
        sender_name = event.get_sender_name()
        target_display = target_name if target_name else f"道友{target_user_id}"
        
        msg = [
            "✅ 转账成功！",
            "━━━━━━━━━━━━━━━",
            f"转出方：{sender_name}",
            f"接收方：{target_display}",
            f"金额：{amount} 灵石",
            "━━━━━━━━━━━━━━━",
            f"💰 你的剩余灵石：{player.gold}"
        ]
        yield event.plain_result("\n".join(msg))

