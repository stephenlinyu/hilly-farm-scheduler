"""
solver.py
GA 算法入口 - 供 app.py 调用
"""

from ga_solver.ga_main import run_ga
from ga_solver.cost_function import cost_function
import datetime


def solve_schedule(machines, fields):
    """
    调度求解器
    输入：
        machines - 农机列表
        fields   - 农田列表
    输出：
        result   - 调度结果
    """
    
    # ===== 1. 构建 model =====
    N = len(machines)
    M = len(fields)
    
    model = {
        'N': N,
        'M': M,
        'mu_u': 20,
        'mu_d': 4,
        'v_max': 30,
        'agents': [],
        'tasks': [],
        'depots': []
    }
    
    # 农机
    for i, m in enumerate(machines):
        model['agents'].append({
            'id': m['id'],
            'x': float(m.get('x', 0)),
            'y': float(m.get('y', 0)),
            'h': float(m.get('h', 300)),
            'nom_vel': float(m.get('nom_vel', 4.0)),
            'fuel': float(m.get('fuel', 0.06)),
            'fueltask': float(m.get('fueltask', 2.0)),
            'w': float(m.get('w', 7000)),
            'depot_id': 1 if i < N // 2 else 2
        })
    
    # 农田
    for j, f in enumerate(fields):
        model['tasks'].append({
            'id': f['id'],
            'x': float(f.get('x', 0)),
            'y': float(f.get('y', 0)),
            'h': float(f.get('h', 300)),
            'S': float(f.get('S', 500))
        })
    
    # 车库
    if N >= 2:
        model['depots'].append({'h': model['agents'][0]['h']})
        model['depots'].append({'h': model['agents'][-1]['h']})
    else:
        model['depots'].append({'h': 300})
        model['depots'].append({'h': 310})
    
    # ===== 2. 运行 GA =====
    best_solution = run_ga(model)
    
    # ===== 3. 计算每台农机的时间 =====
    _, _, _, _, agent_times = cost_function(best_solution['Position'], model)
    
    # ===== 4. 构建结果 =====
    result = {
        'status': 'success',
        'total_cost': best_solution['Cost'],
        'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'agents': []
    }
    
    for i, agent in enumerate(best_solution['Position']['agents']):
        result['agents'].append({
            'machine_id': model['agents'][i]['id'],
            'task_sequence': agent['task'],
            'total_time': agent_times[i]
        })
    
    return result