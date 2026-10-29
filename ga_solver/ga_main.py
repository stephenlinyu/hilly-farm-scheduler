"""
ga_main.py
翻译自 Matlab 的 RunGA.m
遗传算法主循环
"""

import random
import math
import time

from ga_solver.cost_function import cost_function
from ga_solver.init_assignment import init_assignment
from ga_solver.selection import roulette_wheel_selection
from ga_solver.mutate import tubian, mutate_b, mutate_c
from ga_solver.crossover import crossover
from ga_solver.crossover_b import crossover_b


def run_ga(model):
    """
    遗传算法主函数
    """
    
    # ===== GA 参数 =====
    MaxIt = 10000
    nPop = 70
    pt = 0.9
    nt = int(pt * nPop)
    pc = 0.3
    nc = 2 * round(pc * nPop / 2)
    pm = 0.2
    nm = round(pm * nPop)
    beta = 8
    
    # ===== 初始化种群 =====
    empty_individual = {
        'Position': None,
        'gongxian': 0,
        'Cost': float('inf')
    }
    
    pop = [empty_individual.copy() for _ in range(nPop)]
    
    for i in range(nPop):
        pop[i]['Position'] = init_assignment(model)
        cost, gongxian, _, _, _ = cost_function(pop[i]['Position'], model)
        pop[i]['Cost'] = cost
        pop[i]['gongxian'] = gongxian
    
    pop.sort(key=lambda x: x['Cost'])
    
    BestSol = pop[0].copy()
    BestCost = []
    WorstCost = pop[-1]['Cost']
    
    noImproveCount = 0
    bestCostPrev = BestSol['Cost']
    converged = False
    
    start_time = time.time()
    
    for it in range(1, MaxIt + 1):
        
        Costs = [ind['Cost'] for ind in pop]
        P = [math.exp(-beta * c / WorstCost) for c in Costs]
        P_sum = sum(P)
        P = [p / P_sum for p in P]
        
        # ===== 突变（Tubian） =====
        popt = []
        for _ in range(nt):
            k1 = roulette_wheel_selection(P)
            p = pop[k1].copy()
            p['Position'] = tubian(p['Position'], model['M'])
            cost, gongxian, _, _, _ = cost_function(p['Position'], model)
            p['Cost'] = cost
            p['gongxian'] = gongxian
            popt.append(p)
        
        popt.sort(key=lambda x: x['Cost'])
        tubian_population = popt + pop[:nPop - nt]
        
        # ===== 交叉 =====
        popc = []
        for _ in range(nc):
            i1 = roulette_wheel_selection(P)
            i2 = roulette_wheel_selection(P)
            p1 = tubian_population[i1]
            p2 = tubian_population[i2]
            
            prob_crossover = 0.5
            if random.random() < prob_crossover:
                pos = crossover(p1['Position'], p2['Position'], model)
            else:
                pos = crossover_b(p1['Position'], p2['Position'], model)
            
            cost, gongxian, _, _, _ = cost_function(pos, model)
            popc.append({
                'Position': pos,
                'Cost': cost,
                'gongxian': gongxian
            })
        
        popc.sort(key=lambda x: x['Cost'])
        cross_population = pop[:nPop - nc] + popc
        
        # ===== 变异（MutateB / MutateC） =====
        popm = []
        N = len(model['agents'])
        weight = [0.0] * N
        
        for _ in range(nm):
            i = random.randint(0, nPop - 1)
            p = cross_population[i].copy()
            
            # 计算贡献度
            cost, gongxian, _, _, _ = cost_function(p['Position'], model)
            p['Cost'] = cost
            p['gongxian'] = gongxian
            
            # 动态调整权重
            decay_factor = 0.5 * math.exp(-2 * (MaxIt - it) / MaxIt)
            weight = [decay_factor * w + g for w, g in zip(weight, gongxian)]
            probm = [w + 0.1 for w in weight]
            
            # 选择需要变异的农机
            num_selected = max(1, int(math.ceil(N * (MaxIt + 1 - it) / MaxIt)))
            selected_indices = []
            
            if sum(probm) > 0:
                probm_norm = [p / sum(probm) for p in probm]
                for _ in range(min(num_selected, N)):
                    idx = roulette_wheel_selection(probm_norm)
                    selected_indices.append(idx)
                    probm_norm[idx] = 0
                    if sum(probm_norm) > 0:
                        probm_norm = [p / sum(probm_norm) for p in probm_norm]
            
            # ===== MutateB 或 MutateC =====
            prob_mutate = 0.4
            if random.random() < prob_mutate:
                pos = mutate_c(p['Position'], selected_indices)
            else:
                pos = mutate_b(p['Position'], selected_indices)
            
            cost, gongxian, _, _, _ = cost_function(pos, model)
            popm.append({
                'Position': pos,
                'Cost': cost,
                'gongxian': gongxian
            })
        
        popm.sort(key=lambda x: x['Cost'])
        
        # ===== 选择下一代 =====
        pop = [popt[0]] + popc + popm + pop[:nPop - nc - nm - 1]
        pop = pop[:nPop]
        pop.sort(key=lambda x: x['Cost'])
        
        if pop[-1]['Cost'] > WorstCost:
            WorstCost = pop[-1]['Cost']
        
        BestSol = pop[0].copy()
        BestCost.append(BestSol['Cost'])
        
        # ===== 自适应终止判断 =====
        if BestSol['Cost'] < bestCostPrev - 1e-6:
            bestCostPrev = BestSol['Cost']
            noImproveCount = 0
        else:
            noImproveCount += 1
        
        if noImproveCount >= 200:
            converged = True
            print(f'✅ 终止条件达成：连续200次迭代最优成本未改善，停止迭代。')
            break
        
        if it % 10 == 0:
            print(f'Iteration {it} : Best Cost = {BestCost[-1]:.6f}')
    
    if not converged:
        print(f'⚠️ 达到最大迭代次数 {MaxIt}，停止迭代。')
    
    elapsed_time = time.time() - start_time
    print(f'总迭代次数: {len(BestCost)}')
    print(f'耗时: {elapsed_time:.2f} 秒')
    
    return BestSol