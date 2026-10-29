function BestSol = RunGA(model)

%% GA Parameters

MaxIt = 10000;     % 安全最大迭代次数（实际循环可能提前终止）
nPop = 70;         % Population Size
pt = 0.9;
nt = floor(pt*nPop);
pc = 0.3;                 % Crossover Percentage
nc = 2*round(pc*nPop/2);  % Number of Offsprings
pm = 0.2;                 % Mutation Percentage
nm = round(pm*nPop);      % Number of Mutants
beta = 8;                 % Selection Pressure

%% Initialization

empty_individual.Position = [];
empty_individual.gongxian = 0;
empty_individual.Cost = inf;

pop = repmat(empty_individual, nPop, 1);

for i = 1:nPop
    pop(i).Position = InitAssignment(model);
    pop(i).Cost = CostFunction(pop(i).Position, model);
end

% Sort Population
Costs = [pop.Cost];
[Costs, SortOrder] = sort(Costs);
pop = pop(SortOrder);

% Store Best Solution
BestSol = pop(1);
BestCost = zeros(MaxIt, 1);   % 预分配，实际可能用不到那么多
WorstCost = pop(end).Cost;

% ========== 新增：自适应终止控制 ==========
noImproveCount = 0;            % 连续未改善计数器
bestCostPrev = BestSol.Cost;   % 上一次的最优成本
converged = false;             % 是否满足终止条件
% =========================================

%% Main Loop
tic;
for it = 1:MaxIt
    
    % 计算选择概率
    P = exp(-beta*Costs/WorstCost);
    P = P/sum(P);
    
    % ===== 突变 =====
    popt = repmat(empty_individual, nt, 1);
    for k = 1:nt
        k1 = RouletteWheelSelection(P);
        p = pop(k1);
        p.Position = Tubian(p.Position, model.M);
        popt(k) = p;
        popt(k).Cost = CostFunction(popt(k).Position, model);
    end
    Costs = [popt.Cost];
    [~, SortOrder] = sort(Costs);
    popt = popt(SortOrder);
    tubian_Population = [popt; pop(1:nPop-nt)];
    
    % ===== 交叉 =====
    popc = repmat(empty_individual, nc, 1);
    for k = 1:nc
        i1 = RouletteWheelSelection(P);
        i2 = RouletteWheelSelection(P);
        p1 = tubian_Population(i1);
        p2 = tubian_Population(i2);
        
        probCrossover = 0.5;
        if rand() < probCrossover
            popc(k).Position = Crossover(p1.Position, p2.Position, model);
        else
            popc(k).Position = CrossoverB(p1.Position, p2.Position, model);
        end
        popc(k).Cost = CostFunction(popc(k).Position, model);
    end
    Costs = [popc.Cost];
    [~, SortOrder] = sort(Costs);
    popc = popc(SortOrder);
    crossPopulation = [pop(1:nPop-nc); popc];
    
    % ===== 变异 =====
    popm = repmat(empty_individual, nm, 1);
    N = length(model.agents);
    weight = zeros(1, N);
    probm = zeros(1, N);
    for k = 1:nm
        i = randi([1 nPop]);
        p = crossPopulation(i);
        [p.Cost, p.gongxian] = CostFunction(p.Position, model);
        
        decay_factor = 0.5 * exp(-2*(MaxIt-it)/MaxIt);
        weight = decay_factor * weight + p.gongxian;
        weight_factor = 1;
        probm = weight_factor * weight + 0.1;
        
        num_selected = ceil(N*(MaxIt+1-it)/MaxIt);
        selected_indices = [];
        original_indices = 1:length(probm);
        remaining_indices = original_indices;
        probMutateC = probm / sum(probm);
        
        for i_sel = 1:num_selected
            selected_agent_index = RouletteWheelSelection(probMutateC);
            selected_indices = [selected_indices, remaining_indices(selected_agent_index)];
            remaining_indices(selected_agent_index) = [];
            probMutateC(selected_agent_index) = [];
            if sum(probMutateC) > 0
                probMutateC = probMutateC / sum(probMutateC);
            end
        end
        
        probMutate = 0.4;
        if rand() < probMutate
            popm(k).Position = MutateC(p.Position, selected_indices);
        else
            popm(k).Position = MutateB(p.Position, selected_indices);
        end
        popm(k).Cost = CostFunction(popm(k).Position, model);
    end
    Costs = [popm.Cost];
    [~, SortOrder] = sort(Costs);
    popm = popm(SortOrder);
    
    pop = [popt(1); popc; popm; pop(1:nPop-nc-nm-1)];
    
    % 排序
    Costs = [pop.Cost];
    [Costs, SortOrder] = sort(Costs);
    pop = pop(SortOrder);
    
    % 更新 WorstCost
    WorstCost = max(WorstCost, pop(end).Cost);
    
    % 截断
    pop = pop(1:nPop);
    Costs = Costs(1:nPop);
    
    % 更新最佳解
    BestSol = pop(1);
    BestCost(it) = BestSol.Cost;
    
    % ========== 自适应终止判断 ==========
    if BestSol.Cost < bestCostPrev - 1e-6   % 有改善（阈值可调整）
        bestCostPrev = BestSol.Cost;
        noImproveCount = 0;                 % 重置计数器
    else
        noImproveCount = noImproveCount + 1;
    end
    
    if noImproveCount >= 200                % 连续200次未改善
        converged = true;
        BestCost = BestCost(1:it);          % 截断实际迭代次数
        fprintf('? 终止条件达成：连续200次迭代最优成本未改善，停止迭代。\n');
        break;
    end
    % ========================================
    
    % 显示迭代信息（每10次显示一次，避免刷屏）
    if mod(it, 1) == 0
        fprintf('Iteration %d : Best Cost = %.6f\n', it, BestCost(it));
    end
end

% 如果循环自然结束（达到MaxIt），也截断数组
if ~converged
    BestCost = BestCost(1:it);
    fprintf('?? 达到最大迭代次数 %d，停止迭代。\n', MaxIt);
end

% 输出最终结果
[~, ~, total_uphill, total_energy] = CostFunction(BestSol.Position, model);
disp(['最优方案累计爬坡量: ', num2str(total_uphill), ' m']);
disp(['最优方案总能耗: ', num2str(total_energy), ' L']);

elapsedTime = toc;
disp(['Elapsed time for ' num2str(length(BestCost)) ' iterations: ' num2str(elapsedTime) ' seconds']);

end