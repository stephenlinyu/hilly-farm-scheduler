
% % 顺序交叉
function y1 = Crossover(x1, x2, model)
    N = length(x1.agents);  % 农机的数量
    M = model.M;            % 任务总数

    % 生成保留数数组（示例：[1,2,2]）
    max_retain = 3;  % 最大保留数，可根据需要调整
    retainNumbers = randi([1, max_retain], 1, N);
    
    % 初始化子代
    y1 = struct('agents', repmat(struct('task', []), 1, N));
    allocatedTasks = false(1, M);  % 标记已分配的任务

    % 生成随机交叉顺序（例如[2,1,3]）
    crossoverOrder = randperm(N);  
    
    % 复制父代的任务列表（避免修改原始父代）
    x1_tasks = arrayfun(@(a) a.task, x1.agents, 'UniformOutput', false);
    x2_tasks = arrayfun(@(a) a.task, x2.agents, 'UniformOutput', false);
    
    % 步骤1: 按交叉顺序复制基因片段并处理
    for k = 1:N
        agentIdx = crossoverOrder(k);  % 当前处理的agent编号
        
        % 随机选择父代x1或x2的该agent任务片段
        if rand() < 0.5
            selectedTasks = x1_tasks{agentIdx};
        else
            selectedTasks = x2_tasks{agentIdx};
        end
        
        % 应用保留和反转逻辑
        L = length(selectedTasks);
        if L > 0
            % 获取当前agent的保留数，并确保不超过任务长度
            r = min(retainNumbers(agentIdx), L);
            retained = selectedTasks(1:r);          % 保留前r个任务
            reversed = fliplr(selectedTasks(r+1:end));  % 反转剩余任务
            selectedTasks = [retained, reversed];   % 合并保留和反转部分
        end
        
        % 将处理后的任务分配给子代
        y1.agents(agentIdx).task = selectedTasks;
        
        % 标记这些任务为已分配
        allocatedTasks(selectedTasks) = true;
        
        % 从父代所有agent中删除已分配的任务
        for i = 1:N
            x1_tasks{i} = setdiff(x1_tasks{i}, selectedTasks);
            x2_tasks{i} = setdiff(x2_tasks{i}, selectedTasks);
        end
    end

    % 步骤2: 合并父代剩余的任务
    remainingTasksX1 = unique([x1_tasks{:}]);
    remainingTasksX2 = unique([x2_tasks{:}]);
    remainingTasks = union(remainingTasksX1, remainingTasksX2);

    % 步骤3: 将剩余任务随机插入子代
    for task = remainingTasks
        % 随机选择一个agent
        agentIdx = randi(N);
        
        % 随机插入位置
        insertPos = randi([1, length(y1.agents(agentIdx).task) + 1]);
        
        % 插入任务
        y1.agents(agentIdx).task = insertTaskAtIndex(...
            y1.agents(agentIdx).task, task, insertPos);
    end
    
%     for k = 1:N
%         disp(['Agent ', num2str(k), ' tasks: ', num2str(y1.agents(k).task)]);
%     end
end


