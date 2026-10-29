"""
mutate.py
翻译自 Matlab 的 Tubian.m, MutateB.m, MutateC.m
突变算子集合
"""

import random


def tubian(x, model_M):
    """
    跨越（交换）突变算子（Tubian.m）
    随机选择两个农机，交换它们的一部分任务
    """
    nagent = len(x['agents'])
    y = {'agents': [{'task': agent['task'].copy()} for agent in x['agents']]}
    
    # 随机选择两个不同的农机
    a = random.randint(0, nagent - 1)
    b = random.randint(0, nagent - 1)
    while a == b:
        b = random.randint(0, nagent - 1)
    
    tasks_a = y['agents'][a]['task']
    tasks_b = y['agents'][b]['task']
    
    # 如果两个农机都没有任务，直接返回
    if len(tasks_a) == 0 and len(tasks_b) == 0:
        return y
    
    # 如果农机 a 没有任务，从 b 移动一个任务到 a
    if len(tasks_a) == 0 and len(tasks_b) > 0:
        task_to_move = tasks_b.pop(random.randint(0, len(tasks_b) - 1))
        tasks_a.append(task_to_move)
        y['agents'][a]['task'] = tasks_a
        y['agents'][b]['task'] = tasks_b
        return y
    
    # 如果农机 b 没有任务，从 a 移动一个任务到 b
    if len(tasks_b) == 0 and len(tasks_a) > 0:
        task_to_move = tasks_a.pop(random.randint(0, len(tasks_a) - 1))
        tasks_b.append(task_to_move)
        y['agents'][a]['task'] = tasks_a
        y['agents'][b]['task'] = tasks_b
        return y
    
    # 情况1：两个农机都有多个任务
    if len(tasks_a) > 1 and len(tasks_b) > 1:
        start_a = random.randint(0, len(tasks_a) - 2)
        end_a = random.randint(start_a, len(tasks_a) - 1)
        segment_a = tasks_a[start_a:end_a + 1]
        
        start_b = random.randint(0, len(tasks_b) - 2)
        end_b = random.randint(start_b, len(tasks_b) - 1)
        segment_b = tasks_b[start_b:end_b + 1]
        
        y['agents'][a]['task'] = tasks_a[:start_a] + segment_b + tasks_a[end_a + 1:]
        y['agents'][b]['task'] = tasks_b[:start_b] + segment_a + tasks_b[end_b + 1:]
    
    # 情况2：农机 a 有多个任务，农机 b 只有一个任务
    elif len(tasks_a) > 1 and len(tasks_b) == 1:
        start_a = random.randint(0, len(tasks_a) - 2)
        end_a = random.randint(start_a, len(tasks_a) - 1)
        segment_a = tasks_a[start_a:end_a + 1]
        
        y['agents'][b]['task'] = tasks_b + segment_a
        y['agents'][a]['task'] = tasks_a[:start_a] + tasks_a[end_a + 1:]
    
    # 情况3：农机 a 只有一个任务，农机 b 有多个任务
    elif len(tasks_a) == 1 and len(tasks_b) > 1:
        start_b = random.randint(0, len(tasks_b) - 2)
        end_b = random.randint(start_b, len(tasks_b) - 1)
        segment_b = tasks_b[start_b:end_b + 1]
        
        y['agents'][a]['task'] = tasks_a + segment_b
        y['agents'][b]['task'] = tasks_b[:start_b] + tasks_b[end_b + 1:]
    
    # 情况4：两个农机都只有一个任务
    elif len(tasks_a) == 1 and len(tasks_b) == 1:
        task_a = tasks_a[0]
        task_b = tasks_b[0]
        y['agents'][a]['task'] = [task_b]
        y['agents'][b]['task'] = [task_a]
    
    return y


def mutate_b(x, selected_indices):
    """
    MutateB.m：交换两个位置的任务
    从选中的农机中随机选择两个位置，交换它们
    """
    y = {'agents': [{'task': agent['task'].copy()} for agent in x['agents']]}
    
    for idx in selected_indices:
        if idx >= len(y['agents']):
            continue
        tasks = y['agents'][idx]['task']
        if len(tasks) < 2:
            continue
        
        # 随机选择两个位置
        pos1 = random.randint(0, len(tasks) - 2)
        pos2 = random.randint(pos1 + 1, len(tasks) - 1)
        
        # 交换两个位置的任务
        tasks[pos1], tasks[pos2] = tasks[pos2], tasks[pos1]
        y['agents'][idx]['task'] = tasks
    
    return y


def mutate_c(x, selected_indices):
    """
    MutateC.m：反转任务片段
    从选中的农机中随机选择两个位置，反转中间的任务片段
    """
    y = {'agents': [{'task': agent['task'].copy()} for agent in x['agents']]}
    
    for idx in selected_indices:
        if idx >= len(y['agents']):
            continue
        tasks = y['agents'][idx]['task']
        if len(tasks) < 2:
            continue
        
        # 随机选择两个位置
        pos1 = random.randint(0, len(tasks) - 2)
        pos2 = random.randint(pos1 + 1, len(tasks) - 1)
        
        # 确保 pos1 < pos2
        if pos1 > pos2:
            pos1, pos2 = pos2, pos1
        
        # 反转中间片段
        tasks[pos1:pos2 + 1] = reversed(tasks[pos1:pos2 + 1])
        y['agents'][idx]['task'] = tasks
    
    return y