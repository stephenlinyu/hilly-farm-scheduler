"""
cost_function.py
翻译自 Matlab 的 CostFunction.m
计算调度方案的总成本（行驶距离 + 能耗 + 时间）
"""

import math

def cost_function(asg, model):
    """
    成本函数
    输入：
        asg   - 任务分配方案，格式：{'agents': [{'task': [1,2,3]}, ...]}
        model - 模型数据，包含农机和任务的位置、参数
    输出：
        cost         - 总成本
        gongxian     - 贡献度（预留，全0）
        total_uphill - 总上坡量 (m)
        total_energy - 总能耗 (L)
        agent_times  - 每台农机的总时间 (小时)
    """
    
    # 读取参数
    mu_u = model.get('mu_u', 20)
    mu_d = model.get('mu_d', 4)
    v_max = model.get('v_max', 30)
    
    N = len(asg['agents'])
    
    # 读取农机参数
    v_flat = []      # 平路速度, km/h
    eps_flat = []    # 油耗率, L/km
    a_i = []         # 作业能力, m²/h
    e_i = []         # 作业能耗率, L/h
    
    for agent in model['agents']:
        v_flat.append(agent.get('nom_vel', 4.0))
        eps_flat.append(agent.get('fuel', 0.06))
        a_i.append(agent.get('w', 7000))
        e_i.append(agent.get('fueltask', 2.0))
    
    S = [0.0] * N      # 总转移距离 (km)
    E = [0.0] * N      # 总能耗 (L)
    T = [0.0] * N      # 总时间 (h)
    uphill_total = [0.0] * N  # 累计上坡量 (m)
    
    # 遍历每台农机
    for i in range(N):
        tasks = asg['agents'][i].get('task', [])
        ntask = len(tasks)
        if ntask == 0:
            continue
        
        # 获取车库信息
        depot_id = model['agents'][i].get('depot_id', 1)
        # 如果 model 中有 depots 字段
        if 'depots' in model:
            depot_h = model['depots'][depot_id - 1]['h']
        else:
            depot_h = model['agents'][i].get('h', 0)
        
        depot_x = model['agents'][i]['x']
        depot_y = model['agents'][i]['y']
        
        # 上一个点的坐标和高度
        prev_x = depot_x
        prev_y = depot_y
        prev_h = depot_h
        
        # 遍历：车库 -> 任务1 -> ... -> 任务n -> 车库
        for j in range(ntask + 1):
            if j < ntask:
                task_id = tasks[j]
                curr_x = model['tasks'][task_id - 1]['x']
                curr_y = model['tasks'][task_id - 1]['y']
                curr_h = model['tasks'][task_id - 1].get('h', 0)
            else:
                # 最后返回车库
                curr_x = depot_x
                curr_y = depot_y
                curr_h = depot_h
            
            # 计算实际距离 (km)，假设坐标单位为 km
            d = math.sqrt((curr_x - prev_x) ** 2 + (curr_y - prev_y) ** 2)
            if d == 0:
                prev_x = curr_x
                prev_y = curr_y
                prev_h = curr_h
                continue
            
            # 高度差和坡度
            delta_h = curr_h - prev_h          # m
            sin_theta = delta_h / (d * 1000)   # d(km) → m
            # 限制 sin_theta 在 [-1, 1] 内
            sin_theta = max(-1, min(1, sin_theta))
            
            # 坡度能耗率 eps_i(θ)
            if sin_theta >= 0:
                eps_i = eps_flat[i] * (1 + mu_u * sin_theta)
            else:
                eps_i = max(0, eps_flat[i] * (1 + mu_d * sin_theta))
            
            # 坡度速度 v_i(θ)
            if eps_i > 0:
                v_i = min(v_max, (eps_flat[i] * v_flat[i]) / eps_i)
            else:
                v_i = v_max  # 能耗率为0时速度达到最大
            
            # 累积：距离 (km), 能耗 (L), 时间 (h)
            S[i] += d
            E[i] += d * eps_i
            T[i] += d / v_i
            
            # 累计上坡量
            if delta_h > 0:
                uphill_total[i] += delta_h
            
            prev_x = curr_x
            prev_y = curr_y
            prev_h = curr_h
        
        # 作业部分
        for j in range(ntask):
            task_id = tasks[j]
            area = model['tasks'][task_id - 1].get('S', 0)   # m²
            if a_i[i] > 0:
                t_oper = area / a_i[i]       # 作业时间 (h)
            else:
                t_oper = 0
            T[i] += t_oper
            E[i] += t_oper * e_i[i]          # 作业能耗 (L)
    
    # 总成本
    total_S = sum(S)
    total_E = sum(E)
    max_T = 60 * max(T) if T else 0
    cost = 0.42 * total_S + 0.56 * total_E + 0.42 * max_T
    
    # 贡献度（预留）
    gongxian = [0.0] * N
    total_uphill = sum(uphill_total)
    total_energy = 0.06 * total_E
    
    # 返回每台农机的总时间
    agent_times = T
    
    return cost, gongxian, total_uphill, total_energy, agent_times