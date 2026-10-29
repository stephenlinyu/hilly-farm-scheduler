"""
init_assignment.py
翻译自 Matlab 的 InitAssignment.m
生成初始的任务分配方案
"""

import random
import math

def distance(x1, y1, x2, y2):
    """计算两点之间的欧氏距离"""
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

def init_assignment(model):
    """
    初始化任务分配方案
    输入：
        model - 模型数据，包含农机和任务的位置
    输出：
        assignment - 分配方案，格式：{'agents': [{'task': [1,2,3]}, ...]}
    """
    N = model['N']  # 农机数量
    M = model['M']  # 任务数量
    
    # 初始化分配方案：每台农机初始没有任务
    assignment = {'agents': [{'task': []} for _ in range(N)]}
    
    # 标记任务是否已被分配
    allocated = [False] * M
    
    # ===== 第一步：为每台农机分配一个最近的任务 =====
    for i in range(N):
        agent_x = model['agents'][i]['x']
        agent_y = model['agents'][i]['y']
        
        min_dist = float('inf')
        closest_task = -1
        
        for j in range(M):
            if not allocated[j]:
                task_x = model['tasks'][j]['x']
                task_y = model['tasks'][j]['y']
                dist = distance(agent_x, agent_y, task_x, task_y)
                
                if dist < min_dist:
                    min_dist = dist
                    closest_task = j  # 任务索引从 0 开始
        
        if closest_task != -1:
            # 任务 ID 从 1 开始（与 Matlab 保持一致）
            assignment['agents'][i]['task'] = [closest_task + 1]
            allocated[closest_task] = True
    
    # ===== 第二步：分配剩余任务 =====
    remaining_tasks = [j for j in range(M) if not allocated[j]]
    
    while remaining_tasks:
        # 找到当前任务最少的农机
        task_counts = [len(agent['task']) for agent in assignment['agents']]
        min_count = min(task_counts)
        min_agents = [i for i, count in enumerate(task_counts) if count == min_count]
        
        # 随机选择一个任务最少的农机
        selected_agent = random.choice(min_agents)
        
        # 随机选择一个剩余任务
        selected_task = random.choice(remaining_tasks)
        
        # 分配任务（任务 ID 从 1 开始）
        assignment['agents'][selected_agent]['task'].append(selected_task + 1)
        
        # 从剩余列表中移除
        remaining_tasks.remove(selected_task)
    
    return assignment