
function y = MutateC(x, selected_indices)  % x：当前的任务分配方案, mu：变异率, m：任务的总数
    nagent = length(x.agents); % 获取农机的数量
    y = x; % 初始化变异后的方案为原始方案
%     for k=1:nagent
%     disp(['original_Agent ', num2str(k), ' original_tasks: ', num2str(y.agents(k).task)]);
%     end  % for text
    for i=1:length(selected_indices)
    % 被选中的个农机组
    selected_agent = y.agents(selected_indices(i));
    
    % 确保选中的农机组有任务
    if isempty(selected_agent.task)
        return; % 如果农机组没有任务，则不进行变异
    end

    % 从选中的农机组的任务列表中随机选择两个位置
    num_tasks = length(selected_agent.task);
    if num_tasks < 2
        return; % 如果任务数量小于2，则不进行变异
    end

    position1 = randi([1 num_tasks-1]);
    position2 = randi([position1+1 num_tasks]);

    % 确保 position1 < position2
    if position1 > position2
        [position1, position2] = deal(position2, position1);
    end

    % 提取两个位置之间的任务片段
    middle_tasks = selected_agent.task(position1:position2);

    % 反转任务片段
    reversed_tasks = middle_tasks(end:-1:1);

    % 构建新的任务列表，将反转后的任务片段插入到两个位置之间
    new_task_list = [selected_agent.task(1:position1-1), reversed_tasks, selected_agent.task(position2+1:end)];

    % 更新选中农机组的任务列表
    y.agents(selected_indices(i)).task = new_task_list;
    end
%     for k=1:nagent
%     disp(['Agent ', num2str(k), ' tasks: ', num2str(y.agents(k).task)]);
%     end  % for text
end