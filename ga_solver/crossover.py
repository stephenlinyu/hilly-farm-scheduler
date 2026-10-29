"""
crossover.py
翻译自 Matlab 的 Crossover.m 和 insertTaskAtIndex.m
顺序交叉算子
"""

import random

def insert_task_at_index(task_list, task, index):
    """
    在指定位置插入任务（辅助函数）
    对应 Matlab 的 insertTaskAtIndex.m
    """
    return task_list[:index] + [task] + task_list[index:]

def crossover(x1, x2, model):
    """
    顺序交叉算子
    输入：
        x1, x2 - 两个父代个体
        model  - 模型数据（包含农机数量 N 和任务总数 M）
    输出：
        y1     - 子代个体
    """
    N = len(x1['agents'])  # 农机数量
    M = model['M']         # 任务总数
    
    max_retain = 3
    retain_numbers = [random.randint(1, max_retain) for _ in range(N)]
    
    # 初始化子代：每台农机初始没有任务
    y1 = {'agents': [{'task': []} for _ in range(N)]}
    allocated = [False] * M  # 标记任务是否已分配
    
    # 生成随机交叉顺序
    crossover_order = list(range(N))
    random.shuffle(crossover_order)
    
    # 复制父代的任务列表（避免修改原始父代）
    x1_tasks = [agent['task'].copy() for agent in x1['agents']]
    x2_tasks = [agent['task'].copy() for agent in x2['agents']]
    
    # ===== 步骤1：按交叉顺序复制基因片段并处理 =====
    for agentIdx in crossover_order:
        # 随机选择父代 x1 或 x2 的该农机任务片段
        if random.random() < 0.5:
            selected_tasks = x1_tasks[agentIdx].copy()
        else:
            selected_tasks = x2_tasks[agentIdx].copy()
        
        # 应用保留和反转逻辑
        L = len(selected_tasks)
        if L > 0:
            r = min(retain_numbers[agentIdx], L)
            retained = selected_tasks[:r]           # 保留前 r 个任务
            reversed_part = selected_tasks[r:][::-1]  # 反转剩余任务
            selected_tasks = retained + reversed_part
        else:
            selected_tasks = []
        
        # 将处理后的任务分配给子代
        y1['agents'][agentIdx]['task'] = selected_tasks.copy()
        
        # 标记这些任务为已分配
        for task in selected_tasks:
            if 1 <= task <= M:  # 确保任务 ID 在有效范围内
                allocated[task - 1] = True
        
        # 从父代所有农机中删除已分配的任务
        for i in range(N):
            x1_tasks[i] = [t for t in x1_tasks[i] if t not in selected_tasks]
            x2_tasks[i] = [t for t in x2_tasks[i] if t not in selected_tasks]
    
    # ===== 步骤2：合并父代剩余的任务 =====
    remaining_tasks = []
    for i in range(N):
        remaining_tasks.extend(x1_tasks[i])
        remaining_tasks.extend(x2_tasks[i])
    remaining_tasks = list(set(remaining_tasks))  # 去重
    
    # ===== 步骤3：将剩余任务随机插入子代 =====
    for task in remaining_tasks:
        if allocated[task - 1]:
            continue
        # 随机选择一个农机
        agentIdx = random.randint(0, N - 1)
        # 随机插入位置
        insertPos = random.randint(0, len(y1['agents'][agentIdx]['task']))
        # 插入任务
        y1['agents'][agentIdx]['task'] = insert_task_at_index(
            y1['agents'][agentIdx]['task'], task, insertPos
        )
        allocated[task - 1] = True
    
    return y1