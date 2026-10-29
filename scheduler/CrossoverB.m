% %  映射交叉
function y = CrossoverB(x1, x2, model)
    N = length(x1.agents);  % 农机的数量
    M = model.M;            % 任务总数

    % 初始化子代
    y1 = struct('agents', repmat(struct('task', []), 1, N));
    y2 = struct('agents', repmat(struct('task', []), 1, N));
    
    % 生成两个随机数（如1,2）
    randNums = randperm(N, 2);  % 从1~N中随机选择2个不重复的数
    num1 = randNums(1);  % 第一个随机数
    num2 = randNums(2);  % 第二个随机数

    % 步骤1: 复制父代基因片段到子代
    % 子代1的第num1段 = 父代1的第num1段
    y1.agents(num1).task = x1.agents(num1).task;
    % 子代2的第num2段 = 父代2的第num2段
    y2.agents(num2).task = x2.agents(num2).task;

    % 步骤2: 删除父代中与子代相同的基因
    % 从父代1中删除子代2的基因
    for i = 1:N
        x1.agents(i).task = setdiff(x1.agents(i).task, y2.agents(num2).task);
    end
    % 从父代2中删除子代1的基因
    for i = 1:N
        x2.agents(i).task = setdiff(x2.agents(i).task, y1.agents(num1).task);
    end

    % 步骤3: 复制父代剩余基因片段到子代
    % 将父代1的剩余基因片段复制给子代2
    for i = 1:N
        if i ~= num2  % 跳过子代2的第num2段（已复制）
            y2.agents(i).task = x1.agents(i).task;
        end
    end
    % 将父代2的剩余基因片段复制给子代1
    for i = 1:N
        if i ~= num1  % 跳过子代1的第num1段（已复制）
            y1.agents(i).task = x2.agents(i).task;
        end
    end

    % 步骤4: 删除父代中被复制的基因
    % 从父代1中删除已复制给子代2的基因
    for i = 1:N
        x1.agents(i).task = setdiff(x1.agents(i).task, y2.agents(i).task);
    end
    % 从父代2中删除已复制给子代1的基因
    for i = 1:N
        x2.agents(i).task = setdiff(x2.agents(i).task, y1.agents(i).task);
    end

    % 步骤5: 将剩余父代基因随机插入子代
    % 将父代1的剩余基因随机插入子代2
    remainingTasksX1 = unique([x1.agents.task]);
    for task = remainingTasksX1
        agentIdx = randi(N);  % 随机选择一个agent
        insertPos = randi([1, length(y2.agents(agentIdx).task) + 1]);  % 随机插入位置
        y2.agents(agentIdx).task = insertTaskAtIndex(y2.agents(agentIdx).task, task, insertPos);
    end

    % 将父代2的剩余基因随机插入子代1
    remainingTasksX2 = unique([x2.agents.task]);
    for task = remainingTasksX2
        agentIdx = randi(N);  % 随机选择一个agent
        insertPos = randi([1, length(y1.agents(agentIdx).task) + 1]);  % 随机插入位置
        y1.agents(agentIdx).task = insertTaskAtIndex(y1.agents(agentIdx).task, task, insertPos);
    end
    
    if rand() < 0.5
        y = y1;
    else
        y = y2;
    end
end
