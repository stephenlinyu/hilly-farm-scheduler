"""
selection.py
翻译自 Matlab 的 RouletteWheelSelection.m
轮盘赌选择
"""

import random

def roulette_wheel_selection(P):
    """
    轮盘赌选择
    输入：
        P - 概率数组（归一化后，总和为 1）
    输出：
        i - 被选中个体的索引（从 0 开始）
    """
    r = random.random()  # 生成 [0, 1) 之间的随机数
    
    # 计算累计概率
    cumsum = 0.0
    for i, prob in enumerate(P):
        cumsum += prob
        if r <= cumsum:
            return i
    
    # 如果因为浮点误差没有返回，返回最后一个
    return len(P) - 1