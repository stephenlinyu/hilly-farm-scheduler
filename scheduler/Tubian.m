% 跨越（交换）突变算子

function y = Tubian(x,~)
    % 获取代理数量
    nagent = length(x.agents);
    y = x; % 初始化变异后的个体

    % 随机选择两个不同的代理
    a = randi([1 nagent]);
    b = randi([1 nagent]);
    while a == b
        b = randi([1 nagent]); % 确保 a 和 b 不相同
    end

    % 获取两个代理的任务列表
    tasks_a = x.agents(a).task;
    tasks_b = x.agents(b).task;

    % 随机选择两个代理的任务子段进行交换
    % 从代理 a 中选择一个任务子段
    if length(tasks_a) > 1
        start_a = randi([1 length(tasks_a)]);
        end_a = randi([start_a length(tasks_a)]);
        segment_a = tasks_a(start_a:end_a);

        % 从代理 b 中选择一个任务子段
        if length(tasks_b) > 1
            start_b = randi([1 length(tasks_b)]);
            end_b = randi([start_b length(tasks_b)]);
            segment_b = tasks_b(start_b:end_b);

            % 交换两个代理的任务子段
            y.agents(a).task = [tasks_a(1:start_a-1), segment_b, tasks_a(end_a+1:end)];
            y.agents(b).task = [tasks_b(1:start_b-1), segment_a, tasks_b(end_b+1:end)];
        else
            % 如果代理 b 的任务列表长度为 1，直接将代理 a 的任务子段插入到代理 b
            y.agents(b).task = [tasks_b, segment_a];
            y.agents(a).task = [tasks_a(1:start_a-1), tasks_a(end_a+1:end)];
        end
    else
        % 如果代理 a 的任务列表长度为 1，直接将代理 b 的任务子段插入到代理 a
        if length(tasks_b) > 1
            start_b = randi([1 length(tasks_b)]);
            end_b = randi([start_b length(tasks_b)]);
            segment_b = tasks_b(start_b:end_b);

            y.agents(a).task = [tasks_a, segment_b];
            y.agents(b).task = [tasks_b(1:start_b-1), tasks_b(end_b+1:end)];
        else
            % 如果两个代理的任务列表长度都为 1，直接交换两个任务
            y.agents(a).task = tasks_b;
            y.agents(b).task = tasks_a;
        end
    end
%     for k = 1:nagent
%         disp(['Agent ', num2str(k), ' tasks: ', num2str(y.agents(k).task)]);
%     end
end