# core/cultivation_manager.py
import random
import time
from typing import Tuple, Dict

from astrbot.api import AstrBotConfig, logger
from ..config_manager import ConfigManager
from ..models import Player

class CultivationManager:
    def __init__(self, config: AstrBotConfig, config_manager: ConfigManager):
        self.config = config
        self.config_manager = config_manager
        
        # 灵根名称到配置项键的映射
        self.root_to_config_key = {
            # 废柴系列
            "伪": "PSEUDO_ROOT_SPEED",
            
            # 多灵根系列
            "金木水火": "QUAD_ROOT_SPEED",
            "金木水土": "QUAD_ROOT_SPEED",
            "金木火土": "QUAD_ROOT_SPEED",
            "金水火土": "QUAD_ROOT_SPEED",
            "木水火土": "QUAD_ROOT_SPEED",
            
            "金木水": "TRI_ROOT_SPEED",
            "金木火": "TRI_ROOT_SPEED",
            "金木土": "TRI_ROOT_SPEED",
            "金水火": "TRI_ROOT_SPEED",
            "金水土": "TRI_ROOT_SPEED",
            "金火土": "TRI_ROOT_SPEED",
            "木水火": "TRI_ROOT_SPEED",
            "木水土": "TRI_ROOT_SPEED",
            "木火土": "TRI_ROOT_SPEED",
            "水火土": "TRI_ROOT_SPEED",
            
            "金木": "DUAL_ROOT_SPEED",
            "金水": "DUAL_ROOT_SPEED",
            "金火": "DUAL_ROOT_SPEED",
            "金土": "DUAL_ROOT_SPEED",
            "木水": "DUAL_ROOT_SPEED",
            "木火": "DUAL_ROOT_SPEED",
            "木土": "DUAL_ROOT_SPEED",
            "水火": "DUAL_ROOT_SPEED",
            "水土": "DUAL_ROOT_SPEED",
            "火土": "DUAL_ROOT_SPEED",
            
            # 五行单灵根
            "金": "WUXING_ROOT_SPEED",
            "木": "WUXING_ROOT_SPEED",
            "水": "WUXING_ROOT_SPEED",
            "火": "WUXING_ROOT_SPEED",
            "土": "WUXING_ROOT_SPEED",
            
            # 变异灵根
            "雷": "THUNDER_ROOT_SPEED",
            "冰": "ICE_ROOT_SPEED",
            "风": "WIND_ROOT_SPEED",
            "暗": "DARK_ROOT_SPEED",
            "光": "LIGHT_ROOT_SPEED",
            
            # 天灵根（单属性极致）
            "天金": "HEAVENLY_ROOT_SPEED",
            "天木": "HEAVENLY_ROOT_SPEED",
            "天水": "HEAVENLY_ROOT_SPEED",
            "天火": "HEAVENLY_ROOT_SPEED",
            "天土": "HEAVENLY_ROOT_SPEED",
            "天雷": "HEAVENLY_ROOT_SPEED",
            
            # 传说级
            "阴阳": "YIN_YANG_ROOT_SPEED",
            "融合": "FUSION_ROOT_SPEED",
            
            # 神话级
            "混沌": "CHAOS_ROOT_SPEED",
            
            # 禁忌级体质
            "先天道体": "INNATE_BODY_SPEED",
            "神圣体质": "DIVINE_BODY_SPEED"
        }
        
        # 灵根池定义（按权重类别）
        self.root_pools = {
            "PSEUDO": ["伪"],
            "QUAD": ["金木水火", "金木水土", "金木火土", "金水火土", "木水火土"],
            "TRI": ["金木水", "金木火", "金木土", "金水火", "金水土", "金火土", "木水火", "木水土", "木火土", "水火土"],
            "DUAL": ["金木", "金水", "金火", "金土", "木水", "木火", "木土", "水火", "水土", "火土"],
            "WUXING": ["金", "木", "水", "火", "土"],
            "VARIANT": ["雷", "冰", "风", "暗", "光"],
            "HEAVENLY": ["天金", "天木", "天水", "天火", "天土", "天雷"],
            "LEGENDARY": ["阴阳", "融合"],
            "MYTHIC": ["混沌"],
            "DIVINE_BODY": ["先天道体", "神圣体质"]
        }

    def _calculate_base_stats(self, level_index: int) -> Dict[str, int]:
        base_hp = 100 + level_index * 50
        base_attack = 10 + level_index * 8
        base_defense = 5 + level_index * 4
        return {"hp": base_hp, "max_hp": base_hp, "attack": base_attack, "defense": base_defense}

    def _get_random_spiritual_root(self) -> str:
        """基于权重随机抽取灵根"""
        weights_config = self.config.get("SPIRIT_ROOT_WEIGHTS", {})
        
        # 构建权重池
        weight_pool = []
        
        # 伪灵根
        pseudo_weight = weights_config.get("PSEUDO_ROOT_WEIGHT", 1)
        weight_pool.extend([("PSEUDO", root) for root in self.root_pools["PSEUDO"]] * pseudo_weight)
        
        # 四灵根
        quad_weight = weights_config.get("QUAD_ROOT_WEIGHT", 10)
        weight_pool.extend([("QUAD", root) for root in self.root_pools["QUAD"]] * quad_weight)
        
        # 三灵根
        tri_weight = weights_config.get("TRI_ROOT_WEIGHT", 30)
        weight_pool.extend([("TRI", root) for root in self.root_pools["TRI"]] * tri_weight)
        
        # 双灵根
        dual_weight = weights_config.get("DUAL_ROOT_WEIGHT", 100)
        weight_pool.extend([("DUAL", root) for root in self.root_pools["DUAL"]] * dual_weight)
        
        # 五行单灵根
        wuxing_weight = weights_config.get("WUXING_ROOT_WEIGHT", 200)
        weight_pool.extend([("WUXING", root) for root in self.root_pools["WUXING"]] * wuxing_weight)
        
        # 变异灵根
        variant_weight = weights_config.get("VARIANT_ROOT_WEIGHT", 20)
        weight_pool.extend([("VARIANT", root) for root in self.root_pools["VARIANT"]] * variant_weight)
        
        # 天灵根
        heavenly_weight = weights_config.get("HEAVENLY_ROOT_WEIGHT", 5)
        weight_pool.extend([("HEAVENLY", root) for root in self.root_pools["HEAVENLY"]] * heavenly_weight)
        
        # 传说级
        legendary_weight = weights_config.get("LEGENDARY_ROOT_WEIGHT", 2)
        weight_pool.extend([("LEGENDARY", root) for root in self.root_pools["LEGENDARY"]] * legendary_weight)
        
        # 神话级
        mythic_weight = weights_config.get("MYTHIC_ROOT_WEIGHT", 1)
        weight_pool.extend([("MYTHIC", root) for root in self.root_pools["MYTHIC"]] * mythic_weight)
        
        # 禁忌级体质
        divine_weight = weights_config.get("DIVINE_BODY_WEIGHT", 1)
        weight_pool.extend([("DIVINE_BODY", root) for root in self.root_pools["DIVINE_BODY"]] * divine_weight)
        
        if not weight_pool:
            # 兜底方案：默认返回金灵根
            logger.warning("灵根权重池为空，使用默认金灵根")
            return "金"
        
        # 随机选择
        _, selected_root = random.choice(weight_pool)
        return selected_root
    
    def _get_root_description(self, root_name: str) -> str:
        """获取灵根描述"""
        descriptions = {
            "伪": "【废柴】资质低劣，修炼如龟速",
            
            # 四灵根
            "金木水火": "【凡品】四灵根杂乱，资质平庸",
            "金木水土": "【凡品】四灵根杂乱，资质平庸",
            "金木火土": "【凡品】四灵根杂乱，资质平庸",
            "金水火土": "【凡品】四灵根杂乱，资质平庸",
            "木水火土": "【凡品】四灵根杂乱，资质平庸",
            
            # 三灵根
            "金木水": "【凡品】三灵根较杂，资质一般",
            "金木火": "【凡品】三灵根较杂，资质一般",
            "金木土": "【凡品】三灵根较杂，资质一般",
            "金水火": "【凡品】三灵根较杂，资质一般",
            "金水土": "【凡品】三灵根较杂，资质一般",
            "金火土": "【凡品】三灵根较杂，资质一般",
            "木水火": "【凡品】三灵根较杂，资质一般",
            "木水土": "【凡品】三灵根较杂，资质一般",
            "木火土": "【凡品】三灵根较杂，资质一般",
            "水火土": "【凡品】三灵根较杂，资质一般",
            
            # 双灵根
            "金木": "【良品】双灵根，较为常见",
            "金水": "【良品】双灵根，较为常见",
            "金火": "【良品】双灵根，较为常见",
            "金土": "【良品】双灵根，较为常见",
            "木水": "【良品】双灵根，较为常见",
            "木火": "【良品】双灵根，较为常见",
            "木土": "【良品】双灵根，较为常见",
            "水火": "【良品】双灵根，较为常见",
            "水土": "【良品】双灵根，较为常见",
            "火土": "【良品】双灵根，较为常见",
            
            # 五行单灵根
            "金": "【上品】金之精华，锋锐无双",
            "木": "【上品】木之生机，生生不息",
            "水": "【上品】水之灵韵，柔中带刚",
            "火": "【上品】火之烈焰，霸道无匹",
            "土": "【上品】土之厚重，稳如磐石",
            
            # 变异灵根
            "雷": "【稀有】天地雷霆，毁灭之力",
            "冰": "【稀有】极寒冰封，万物凝固",
            "风": "【稀有】疾风骤雨，来去无踪",
            "暗": "【稀有】幽暗深邃，诡异莫测",
            "光": "【稀有】神圣光明，普照万物",
            
            # 天灵根
            "天金": "【极品】天选之子，金之极致",
            "天木": "【极品】天选之子，木之极致",
            "天水": "【极品】天选之子，水之极致",
            "天火": "【极品】天选之子，火之极致",
            "天土": "【极品】天选之子，土之极致",
            "天雷": "【极品】天选之子，雷之极致",
            
            # 传说级
            "阴阳": "【传说】阴阳调和，造化玄机",
            "融合": "【传说】五行融合，万法归一",
            
            # 神话级
            "混沌": "【神话】混沌初开，包罗万象",
            
            # 禁忌级
            "先天道体": "【禁忌】天生道体，与天地同寿",
            "神圣体质": "【禁忌】神之后裔，天赋异禀"
        }
        return descriptions.get(root_name, "【未知】神秘的灵根")

    def generate_new_player_stats(self, user_id: str) -> Player:
        root = self._get_random_spiritual_root()
        initial_stats = self._calculate_base_stats(0)
        return Player(
            user_id=user_id,
            spiritual_root=f"{root}灵根",
            gold=self.config["VALUES"]["INITIAL_GOLD"],
            **initial_stats
        )

    def handle_check_in(self, player: Player) -> Tuple[bool, str, Player]:
        now = time.time()
        if now - player.last_check_in < 22 * 60 * 60:
            return False, "道友，今日已经签到过了，请明日再来。", player

        reward = random.randint(self.config["VALUES"]["CHECK_IN_REWARD_MIN"], self.config["VALUES"]["CHECK_IN_REWARD_MAX"])
        p_clone = player.clone()
        p_clone.gold += reward
        p_clone.last_check_in = now

        msg = f"签到成功！获得灵石 x{reward}。道友当前的家底为 {p_clone.gold} 灵石。"
        return True, msg, p_clone

    def handle_start_cultivation(self, player: Player) -> Tuple[bool, str, Player]:
        if player.state != "空闲":
            return False, f"道友当前正在「{player.state}」中，无法分心闭关。", player

        p_clone = player.clone()
        p_clone.state = "修炼中"
        p_clone.state_start_time = time.time()

        msg = "道友已进入冥想状态，开始闭关修炼。使用「出关」可查看修炼成果。"
        return True, msg, p_clone

    def handle_end_cultivation(self, player: Player) -> Tuple[bool, str, Player]:
        if player.state != "修炼中":
            return False, "道友尚未开始闭关，何谈出关？", player

        now = time.time()
        duration_minutes = (now - player.state_start_time) / 60

        p_clone = player.clone()
        p_clone.state = "空闲"
        p_clone.state_start_time = 0.0

        if duration_minutes < 1:
            msg = "道友本次闭关不足一分钟，未能有所精进。下次要更有耐心才是。"
            return True, msg, p_clone

        player_root_name = p_clone.spiritual_root.replace("灵根", "")
        config_key = self.root_to_config_key.get(player_root_name, "WUXING_ROOT_SPEED")
        speed_multiplier = self.config["SPIRIT_ROOT_SPEEDS"].get(config_key, 1.0)
        
        base_exp_per_min = self.config["VALUES"]["BASE_EXP_PER_MINUTE"]
        exp_gained = int(duration_minutes * base_exp_per_min * speed_multiplier)
        p_clone.experience += exp_gained

        # 计算回血
        hp_recovery_ratio = self.config["VALUES"].get("CULTIVATION_HP_RECOVERY_RATIO", 0.0)
        hp_recovered = int(exp_gained * hp_recovery_ratio)
        hp_before = p_clone.hp
        p_clone.hp = min(p_clone.max_hp, p_clone.hp + hp_recovered)
        hp_actually_recovered = p_clone.hp - hp_before

        speed_info = f"（灵根加成: {speed_multiplier:.2f}倍）"
        msg_parts = [
            f"道友本次闭关共持续 {int(duration_minutes)} 分钟,",
            f"修为增加了 {exp_gained} 点！{speed_info}",
        ]
        if hp_actually_recovered > 0:
            msg_parts.append(f"闭关吐纳间，气血恢复了 {hp_actually_recovered} 点。")
        
        msg_parts.append(f"当前总修为：{p_clone.experience}")
        
        msg = "\n".join(msg_parts)
        return True, msg, p_clone

    def handle_breakthrough(self, player: Player) -> Tuple[bool, str, Player]:
        current_level_index = player.level_index
        p_clone = player.clone()

        if current_level_index >= len(self.config_manager.level_data) - 1:
            return False, "道友已臻化境，达到当前世界的顶峰，无法再进行突破！", p_clone

        next_level_info = self.config_manager.level_data[current_level_index + 1]
        exp_needed = next_level_info['exp_needed']
        success_rate = next_level_info['success_rate']

        if p_clone.experience < exp_needed:
            msg = (f"突破失败！\n目标境界：{next_level_info['level_name']}\n"
                   f"所需修为：{exp_needed} (当前拥有 {p_clone.experience})")
            return False, msg, p_clone

        if random.random() < success_rate:
            p_clone.level_index = current_level_index + 1
            p_clone.experience -= exp_needed

            new_stats = self._calculate_base_stats(p_clone.level_index)
            p_clone.hp = new_stats['hp']
            p_clone.max_hp = new_stats['max_hp']
            p_clone.attack = new_stats['attack']
            p_clone.defense = new_stats['defense']

            msg = (f"恭喜道友！天降祥瑞，突破成功！\n"
                   f"当前境界已达：【{p_clone.get_level(self.config_manager)}】\n"
                   f"生命值提升至 {p_clone.max_hp}，攻击提升至 {p_clone.attack}，防御提升至 {p_clone.defense}！\n"
                   f"剩余修为: {p_clone.experience}")
        else:
            punishment = int(exp_needed * self.config["VALUES"]["BREAKTHROUGH_FAIL_PUNISHMENT_RATIO"])
            p_clone.experience -= punishment
            msg = (f"可惜！道友在突破过程中气息不稳，导致失败。\n"
                   f"境界稳固在【{p_clone.get_level(self.config_manager)}】，但修为空耗 {punishment} 点。\n"
                   f"剩余修为: {p_clone.experience}")

        return True, msg, p_clone
    
    def handle_reroll_spirit_root(self, player: Player) -> Tuple[bool, str, Player]:
        cost = self.config["VALUES"].get("REROLL_SPIRIT_ROOT_COST", 10000)
        
        if player.gold < cost:
            return False, f"重入仙途乃逆天之举，需消耗 {cost} 灵石，道友的家底还不够。", player

        p_clone = player.clone()
        p_clone.gold -= cost
        
        old_root = p_clone.spiritual_root
        new_root_name = self._get_random_spiritual_root()
        p_clone.spiritual_root = f"{new_root_name}灵根"
        
        # 获取新灵根描述
        new_root_desc = self._get_root_description(new_root_name)

        msg = (f"✨ 逆天改命成功！\n"
               f"━━━━━━━━━━━━━━━\n"
               f"耗费灵石：{cost}\n"
               f"原有灵根：{old_root}\n"
               f"新的灵根：{p_clone.spiritual_root}\n"
               f"评价：{new_root_desc}\n"
               f"━━━━━━━━━━━━━━━\n"
               f"祝道友仙途坦荡，大道可期！")
        return True, msg, p_clone