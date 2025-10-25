#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
境界压制功能测试脚本
"""

import random
import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_level_advantage():
    """
    测试境界压制功能
    """
    print("=== 境界压制功能测试 ===")
    
    # 模拟玩家和Boss的境界差
    test_cases = [
        (8, 5),   # 玩家搬血境(8) vs Boss炼气五层(5) - 差3个境界
        (10, 5),  # 玩家化灵境(10) vs Boss炼气五层(5) - 差5个境界
        (5, 8),   # 玩家炼气五层(5) vs Boss搬血境(8) - 差-3个境界
        (15, 10), # 玩家真一境(15) vs Boss化灵境(10) - 差5个境界
    ]
    
    for player_level, boss_level in test_cases:
        level_advantage = player_level - boss_level
        print(f"\n玩家境界: {player_level}, Boss境界: {boss_level}, 境界差: {level_advantage}")
        
        if level_advantage >= 3:
            print("  满足境界压制条件")
            # 模拟10次战斗，统计触发概率
            instant_kill_count = 0
            test_count = 1000
            
            for _ in range(test_count):
                if random.random() < 0.3:  # 30%概率
                    instant_kill_count += 1
            
            actual_rate = instant_kill_count / test_count
            print(f"  1000次测试中触发境界压制: {instant_kill_count}次, 实际概率: {actual_rate:.2%}")
        else:
            print("  不满足境界压制条件")

if __name__ == "__main__":
    test_level_advantage()