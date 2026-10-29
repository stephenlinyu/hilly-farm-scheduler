
clc;   %清除命令窗口
clear;  %清除工作区
close all;  %关闭图形窗口

%% Problem Definition

model = CreateModel();  %调用CreateModel.m函数创建模型，初始化智能体和任务
% load('modelTest3.mat');

%% GA Parameters

MaxIt = 500;     % Maximum Number of Iterationsv
nPop = 70;       % Population Size
pt = 0.9;
nt = floor(pt*nPop);
pc = 0.3;                 % Crossover Percentage
nc = 2*round(pc*nPop/2);  % Number of Offsprings (also Parnets)...
pm = 0.2;                 % Mutation Percentage
nm = round(pm*nPop);      % Number of Mutants   round函数用作四舍五入取整数，若出现中间值2.5，取最近偶数2
beta = 8;                 % Selection Pressure: for exponential distribution 选择压力，用于指数分布
% pause(0.01); % Due to a bug in older versions of MATLAB

%% Initialization

empty_individual.Position = [];
empty_individual.gongxian = 0;
empty_individual.Cost = inf;  % 初始化一个空个体empty_individual，其位置为空，成本为无穷大

pop = repmat(empty_individual, nPop, 1); % 重复数组函数，empty_individual是要重复的数组，nPop 和 1 分别是沿行和列方向的重复次数
                                         % 注意：重复1次表示不变，使用repmat函数创建一个种群pop，包含nPop个这样的空个体
% A = [1 2 3];
% B = repmat(A, 1, 2);
% disp(B); 
% 1     2     3     1     2     3   % 示例
for i = 1:nPop

    % Initialize Position
    pop(i).Position = InitAssignment(model);  % 生成一个初始的任务分配方案
    % Evaluation
    pop(i).Cost = CostFunction(pop(i).Position,model);  % InitAssignment(model)函数被用来初始化种群中每个个体的位置（即任务分配方案），然后这个初始的任务分配方案被传递给CostFunction来计算成本

end

% Sort Population
Costs = [pop.Cost];   % 创建了一个包含所有个体成本的数组 Costs;方括号 [...] 可以将结构体数组中的某个字段提取出来，形成一个普通的数组
[Costs, SortOrder] = sort(Costs); % sort 函数对数组进行排序（一般升序），并返回排序后的数组和排序的索引; 
% 假设Costs=[5, 2, 8, 3];
% Costs=[2, 3, 5, 8];
% SortOrder=[2, 4, 1, 3];

pop = pop(SortOrder); % 使用 SortOrder 索引来重排种群数组 ,如pop(1).cost=2，pop(2)=3

% Store Best Solution
BestSol = pop(1);
% Array to Hold Best Cost Values
BestCost = zeros(MaxIt, 1); 
% Store Cost
WorstCost = pop(end).Cost;

%% Main Loop
tic;
for it = 1:MaxIt

    % Calculate Selection Probabilities
    P = exp(-beta*Costs/WorstCost);  % 使用指数函数计算每个个体的选择概率
    P = P/sum(P);  % 择概率通过除以总和进行归一化，确保所有概率之和为1
    
    % 突变算子
    popt = repmat(empty_individual,nt,1);
    for k = 1:nt
        k1 = RouletteWheelSelection(P);
        p = pop(k1);
        p.Position = Tubian(p.Position,model.M); 
        popt(k) = p;
        popt(k).Cost = CostFunction(popt(k).Position,model);
    end
    Costs = [popt.Cost];   
    [~, SortOrder] = sort(Costs); % sort 函数对数组进行排序（一般升序），并返回排序后的数组和排序的索引; 
    popt = popt(SortOrder); % 使用 SortOrder 索引来重排种群数组 
    tubian_Population = [popt;pop(1:nPop-nt)];
    
    % Crossover
    popc = repmat(empty_individual, nc, 1); % 创建一个新的种群 popc，这个种群将存储通过交叉操作生成的后代个体
    for k = 1:nc
        
        % Select Parents Indices
        i1 = RouletteWheelSelection(P);  % 函数根据个体的选择概率P选择两个父代
        i2 = RouletteWheelSelection(P);
    
        % Select Parents
%         p1 = pop(i1);  % 根据索引选择两个父代
%         p2 = pop(i2);
        p1 = tubian_Population(i1);  % 根据索引选择两个父代
        p2 = tubian_Population(i2);
        
        % Apply Crossover
         % 假设有概率阈值，分别对应函数的执行概率
        probCrossover = 0.5; % 函数的执行概率%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
        
        if rand() < probCrossover
            popc(k).Position = Crossover(p1.Position, p2.Position, model);
        else
            popc(k).Position = CrossoverB(p1.Position, p2.Position, model);
        end

        % Evaluate Offsprings
        popc(k).Cost = CostFunction(popc(k).Position,model);
        
    end
      Costs = [popc.Cost];   
      [~, SortOrder] = sort(Costs); % sort 函数对数组进行排序（一般升序），并返回排序后的数组和排序的索引; 
      popc = popc(SortOrder); % 使用 SortOrder 索引来重排种群数组 ,如pop(1).cost=2，pop(2)=3
      crossPopulation = [pop(1:nPop-nc); popc];  %  将子代与成本较低的父代构成交叉种群
      
    % Mutation
      p = repmat(empty_individual, nm, 1);
      popm = repmat(empty_individual, nm, 1); % 使用repmat函数创建变异种群，数量是变异个体数量nm
      N = length(model.agents); 
      weight=zeros(1, N);
      probm=zeros(1, N);
    for k = 1:nm
        
        % Select Parent
        i = randi([1 nPop]); % randi with value from 1 to nPop
        p = crossPopulation(i); % 通过索引 i 从种群 pop 中选择第 i 个个体
        % Apply Mutation
        % 计算贡献
        [p.Cost, p.gongxian] = CostFunction(p.Position, model);
%         disp(['p.gongxian: ', num2str(p.gongxian)]);
    
        % 动态调整 weight 的衰减系数
        % 指数
        decay_factor = 0.5 * exp(-2 *( MaxIt-it) / MaxIt); %%%%%%%%%%%%%%%%%%%%%
%         % 线性
%         decay_factor = 0.7*(it/MaxIt);
%         % 三角
%         decay_factor = 0.7*sin(0.5*pi*(it/MaxIt));
        
        weight =decay_factor*weight+p.gongxian; 
%         disp([ ' weight: ', num2str(weight)]);

        weight_factor = 1;
        probm=weight_factor*weight+0.1;   % 
%         disp([ ' probm: ', num2str(probm)]);  
        % 初始选择数量，可以根据需要调整
        num_selected = ceil(N*(MaxIt+1-it)/MaxIt); 
        selected_indices = []; % 存储已选择的个体索引
        % 原始个体的索引
        original_indices = 1:length(probm);
        % 初始剩余个体的索引
        remaining_indices = original_indices;
        % 归一化变异概率
        probMutateC= probm/sum(probm);
        
        for i = 1:num_selected
        % 使用轮盘赌方法选择需要变异的个体
        selected_agent_index = RouletteWheelSelection(probMutateC);
        % 将选中的个体索引添加到列表中
        selected_indices = [selected_indices,remaining_indices( selected_agent_index)];
        % 从剩余个体的索引中移除已选择的个体
        remaining_indices(selected_agent_index) = [];
        % 从概率数组中移除已选择的个体
        probMutateC(selected_agent_index) = [];
        % 重新归一化剩余的概率
           if sum(probMutateC) > 0
        probMutateC = probMutateC / sum(probMutateC);
           end
        end

        % 对选中的个体进行变异
        probMutate =0.4; %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
        if rand() <probMutate
           popm(k).Position = MutateC(p.Position, selected_indices);
        else
           popm(k).Position = MutateB(p.Position, selected_indices);
        end
        
        % Evaluate Mutant
        popm(k).Cost = CostFunction(popm(k).Position,model);
%     disp(['Individual1 ', num2str(length(pop(1:nPop-nc-nm)))]);
%     disp(['Individual2 ', num2str(length(popc))]);
%     disp(['Individual3 ', num2str(length(popm))]);

    end
      Costs = [popm.Cost];   
      [~, SortOrder] = sort(Costs); % sort 函数对数组进行排序（一般升序），并返回排序后的数组和排序的索引; 
      popm = popm(SortOrder); % 使用 SortOrder 索引来重排种群数组 ,如pop(1).cost=2，pop(2)=3
      
      pop = [popt(1);popc;popm;pop(1:nPop-nc-nm-1)];
%       pop = [popt(1);popc;popm(1:end-2);pop(1)];

    % Sort Population
    Costs = [pop.Cost];
    [Costs, SortOrder] = sort(Costs);
    pop = pop(SortOrder); % sort the pop base on index in SortOrder
    
    % Update Worst Cost
    WorstCost = max(WorstCost, pop(end).Cost);
    
    % Truncation
    pop = pop(1:nPop); % 将种群 pop 中从第一个到第 nPop 个个体（即整个种群）赋值给 pop
    Costs = Costs(1:nPop);
    
    % Store Best Solution Ever Found
    BestSol = pop(1);
    
    % Store Best Cost Ever Found
    BestCost(it) = BestSol.Cost; % BestCost 是一个数组，长度通常与迭代次数 it 相等
    % BestSol 是当前迭代中找到的最佳个体，通常是一个结构体，包含了任务分配方案和成本值
    
    % Show Iteration Information
     disp(['Iteration ' num2str(it) ': Best Cost = ' num2str(BestCost(it))]); % it 索引用于访问第 it 次迭代的最佳成本值
     % num2str 函数，用于将数字转换为字符串，并保留两位小数点，即使数字是整数；使用方括号 [ ] 连接多个字符串和变量，创建一个完整的输出字符串
%      it=20;BestCost=80;
%     outputStr = sprintf('Iteration %d: Best Cost = %0.2f', it, BestCost);
%     disp(outputStr);
end
[~, ~, total_uphill, total_energy] = CostFunction(BestSol.Position, model);
disp(['最优方案累计爬坡量: ', num2str(total_uphill), ' m']);
disp(['最优方案总能耗: ', num2str(total_energy), ' L']);

elapsedTime = toc;
disp(['Elapsed time for ' num2str(MaxIt) ' iterations: ' num2str(elapsedTime) ' seconds']);
%% Results
PlotAssignments(model, BestSol.Position, 1); % 传入模型 model、当前找到的最佳解 BestSol.Position 和一个图形窗口编号 1

 figure; % 创建一个新的图形窗口
 semilogy(BestCost, 'LineWidth', 2); % 使用 semilogy 函数绘制最佳成本 BestCost 随迭代次数的变化。semilogy 函数绘制垂直线图，其中 BestCost 是一个数组，'LineWidth', 2 设置线宽为 2 个像素
 plot(BestCost,'r', 'LineWidth', 2); % plot 函数绘制水平线图
 xlabel('Iteration');
 ylabel('Cost');
 legend('改进');
 grid on;  % 打开网格，以便更容易读取图形中的数据点
