"""
crossover_b.py
翻译自 Matlab 的 CrossoverB.m
映射交叉算子（修复版）
"""

import random

def insert_task_at_index(task_list, task, index):
    """在指定位置插入任务（辅助函数）"""
    return task_list[:index] + [task] + task_list[index:]

def crossover_b(x1, x2, model):
    """
    映射交叉算子
    输入：
        x1, x2 - 两个父代个体
        model  - 模型数据（包含农机数量 N 和任务总数 M）
    输出：
        y      - 子代个体（随机选择 y1 或 y2）
    """
    N = len(x1['agents'])  # 农机数量
    M = model['M']         # 任务总数
    
    # 深拷贝父代，避免修改原始数据
    x1_copy = {'agents': [{'task': agent['task'].copy()} for agent in x1['agents']]}
    x2_copy = {'agents': [{'task': agent['task'].copy()} for agent in x2['agents']]}
    
    # 初始化两个子代
    y1 = {'agents': [{'task': []} for _ in range(N)]}
    y2 = {'agents': [{'task': []} for _ in range(N)]}
    
    # 生成两个随机数（选择两个不同的农机）
    rand_nums = random.sample(range(N), 2)
    num1 = rand_nums[0]
    num2 = rand_nums[1]
    
    # 记录已分配的任务（用于去重）
    allocated1 = set()
    allocated2 = set()
    
    # ===== 步骤1：复制父代基因片段到子代 =====
    # 子代1 的第 num1 段 = 父代1 的第 num1 段
    tasks1 = x1_copy['agents'][num1]['task'].copy()
    y1['agents'][num1]['task'] = tasks1.copy()
    allocated1.update(tasks1)
    
    # 子代2 的第 num2 段 = 父代2 的第 num2 段
    tasks2 = x2_copy['agents'][num2]['task'].copy()
    y2['agents'][num2]['task'] = tasks2.copy()
    allocated2.update(tasks2)
    
    # ===== 步骤2：删除父代中已分配的任务 =====
    for i in range(N):
        x1_copy['agents'][i]['task'] = [t for t in x1_copy['agents'][i]['task'] if t not in allocated2]
        x2_copy['agents'][i]['task'] = [t for t in x2_copy['agents'][i]['task'] if t not in allocated1]
    
    # ===== 步骤3：将父代剩余基因复制到子代 =====
    for i in range(N):
        if i != num2:
            # 子代2 从父代1 复制（跳过 num2）
            copied_tasks = [t for t in x1_copy['agents'][i]['task'] if t not in allocated2]
            y2['agents'][i]['task'] = copied_tasks.copy()
            allocated2.update(copied_tasks)
        
        if i != num1:
            # 子代1 从父代2 复制（跳过 num1）
            copied_tasks = [t for t in x2_copy['agents'][i]['task'] if t not in allocated1]
            y1['agents'][i]['task'] = copied_tasks.copy()
            allocated1.update(copied_tasks)
    
    # ===== 步骤4：收集所有剩余未分配的任务 =====
    all_tasks = set(range(1, M + 1))
    remaining1 = list(all_tasks - allocated1)
    remaining2 = list(all_tasks - allocated2)
    
    # ===== 步骤5：将剩余任务随机插入子代 =====
    # 插入子代1
    for task in remaining1:
        agent_idx = random.randint(0, N - 1)
        insert_pos = random.randint(0, len(y1['agents'][agent_idx]['task']))
        y1['agents'][agent_idx]['task'] = insert_task_at_index(
            y1['agents'][agent_idx]['task'], task, insert_pos
        )
    
    # 插入子代2
    for task in remaining2:
        agent_idx = random.randint(0, N - 1)
        insert_pos = random.randint(0, len(y2['agents'][agent_idx]['task']))
        y2['agents'][agent_idx]['task'] = insert_task_at_index(
            y2['agents'][agent_idx]['task'], task, insert_pos
        )
    
    # 随机选择一个子代返回
    if random.random() < 0.5:
        return y1
    else:
        return y2