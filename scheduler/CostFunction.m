function [cost, gongxian, total_uphill, total_energy, agent_times] = CostFunction(asg, model)
    % ============================================================
    % 成本函数
    % 输入：
    %   asg   - 任务分配方案
    %   model - 模型数据
    % 输出：
    %   cost         - 总成本
    %   gongxian     - 贡献度（预留）
    %   total_uphill - 总上坡量
    %   total_energy - 总能耗
    %   agent_times  - 每台农机的总时间（小时）← 新增
    % ============================================================
    
    % 读取参数
    mu_u = model.mu_u;
    mu_d = model.mu_d;
    v_max = model.v_max;
    
    N = length(asg.agents);
    v_flat = [model.agents(:).nom_vel];          % 平路速度, km/h
    eps_flat = [model.agents(:).fuel];           % ε_{0,i}, L/km
    a_i = [model.agents(:).w];                   % 作业能力, m?/h
    e_i = [model.agents(:).fueltask];            % 作业能耗率, L/h
    
    S = zeros(1, N);     % 总转移距离 (km)
    E = zeros(1, N);     % 总能耗 (L)
    T = zeros(1, N);     % 总时间 (h)
    uphill_total = zeros(1, N);  % 累计上坡量 (m)
    
    for i = 1:N
        ntask = length(asg.agents(i).task);
        if ntask == 0
            continue;
        end
        
        vtask = asg.agents(i).task;
        % 获取车库信息
        depot_id = model.agents(i).depot_id;
        depot_h = model.depots(depot_id).h;
        depot_x = model.agents(i).x;
        depot_y = model.agents(i).y;
        
        % 上一个点的坐标和高度
        prev_x = depot_x;
        prev_y = depot_y;
        prev_h = depot_h;
        
        for j = 1:(ntask+1)   % 遍历：车库->任务1 -> ... -> 任务n -> 车库
            if j <= ntask
                task_id = vtask(j);
                curr_x = model.tasks(task_id).x;
                curr_y = model.tasks(task_id).y;
                curr_h = model.tasks(task_id).h;
            else   % 最后返回车库
                curr_x = depot_x;
                curr_y = depot_y;
                curr_h = depot_h;
            end
            
            % 计算实际距离 (km)，假设坐标单位为 km
            d = sqrt((curr_x - prev_x)^2 + (curr_y - prev_y)^2);
            if d == 0
                prev_x = curr_x; prev_y = curr_y; prev_h = curr_h;
                continue;
            end
            
            % 高度差和坡度
            delta_h = curr_h - prev_h;          % m
            sin_theta = delta_h / (d * 1000);   % d(km) → m
            % 限制 sin_theta 在 [-1,1] 内（避免数值误差）
            sin_theta = max(-1, min(1, sin_theta));
            
            % 坡度能耗率 ε_i(θ)
            if sin_theta >= 0
                eps_i = eps_flat(i) * (1 + mu_u * sin_theta);
            else
                eps_i = max(0, eps_flat(i) * (1 + mu_d * sin_theta));
            end
            
            % 坡度速度 v_i(θ)
            if eps_i > 0
                v_i = min(v_max, (eps_flat(i) * v_flat(i)) / eps_i);
            else
                v_i = v_max;   % 能耗率为0时速度达到最大
            end
            
            % 累积：距离 (km), 能耗 (L), 时间 (h)
            S(i) = S(i) + d;
            E(i) = E(i) + d * eps_i;
            T(i) = T(i) + d / v_i;
            
            % 累计上坡量
            if delta_h > 0
                uphill_total(i) = uphill_total(i) + delta_h;
            end
            
            prev_x = curr_x; prev_y = curr_y; prev_h = curr_h;
        end
        
        % 作业部分
        for j = 1:ntask
            task_id = vtask(j);
            area = model.tasks(task_id).S;        % m?
            t_oper = area / a_i(i);               % 作业时间 (h)
            T(i) = T(i) + t_oper;
            E(i) = E(i) + t_oper * e_i(i);        % 作业能耗 (L)
        end
    end
    
    % 总成本
    total_S = sum(S);
    total_E = sum(E);
    max_T = 60 * max(T);
    cost = 0.42 * total_S + 0.56 * total_E + 0.42 * max_T;
    
    % 贡献度（各机器占总成本的比例，供 GA 某些地方使用）
    gongxian = zeros(1, N);   % 如果需要可以重新定义，这里先留空
    total_uphill = sum(uphill_total);
    total_energy = 0.06 * total_E;
    
    % ============================================================
    % ? 新增：返回每台农机的总时间（单位：小时）
    % ============================================================
    agent_times = T;  % T 是每台农机的总时间数组 (小时)
    
end