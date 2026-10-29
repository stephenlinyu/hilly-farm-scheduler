% run_scheduler.m
clc;
clear;
close all;

% 自动切换到脚本所在目录
[script_path, ~, ~] = fileparts(mfilename('fullpath'));
cd(script_path);

disp('========================================');
disp('   农机调度系统 - Matlab 计算引擎');
disp('========================================');

% 检查 CSV 文件是否存在
if ~exist('machines.csv', 'file') || ~exist('fields.csv', 'file')
    error('? 未找到 CSV 数据文件，请先在网页中点击"智能调度"导出数据');
end

% 1. 读取数据
disp('1. 读取 CSV 数据...');
model = ReadData();

% 2. 运行遗传算法
disp('2. 运行遗传算法...');
BestSol = RunGA(model);

% 3. 构建结果（包含每台农机的时间）
disp('3. 构建调度结果...');

% 先计算每台农机的详细成本（包含时间）
[~, ~, ~, ~, agent_times] = CostFunction(BestSol.Position, model);

result.agents = [];
for i = 1:model.N
    task_list = BestSol.Position.agents(i).task;
    result.agents(i).machine_id = model.agents(i).machine_id;
    result.agents(i).task_sequence = task_list;
    result.agents(i).total_time = agent_times(i);  % 总时间（小时）
end
result.total_cost = BestSol.Cost;
result.status = 'success';
result.timestamp = datestr(now, 'yyyy-mm-dd HH:MM:SS');

% 4. 手动构建 JSON 字符串（兼容 R2016a）
disp('4. 保存 result.json...');
json_str = '{';
json_str = [json_str '"status":"success",'];
json_str = [json_str '"total_cost":' num2str(result.total_cost, '%.6f') ','];
json_str = [json_str '"timestamp":"' result.timestamp '",'];
json_str = [json_str '"agents":['];
for i = 1:length(result.agents)
    json_str = [json_str '{'];
    json_str = [json_str '"machine_id":"' result.agents(i).machine_id '",'];
    json_str = [json_str '"total_time":' num2str(result.agents(i).total_time, '%.3f') ','];
    json_str = [json_str '"task_sequence":['];
    tasks = result.agents(i).task_sequence;
    if isempty(tasks)
        json_str = [json_str ']'];
    else
        for j = 1:length(tasks)
            json_str = [json_str num2str(tasks(j))];
            if j < length(tasks)
                json_str = [json_str ','];
            end
        end
        json_str = [json_str ']'];
    end
    if i < length(result.agents)
        json_str = [json_str '},'];
    else
        json_str = [json_str '}'];
    end
end
json_str = [json_str ']}'];

% 写入文件
fid = fopen('result.json', 'w');
fprintf(fid, '%s', json_str);
fclose(fid);

disp('========================================');
disp('? 调度完成！结果已保存到 result.json');
fprintf('   总成本: %.6f\n', result.total_cost);
fprintf('   农机数: %d\n', length(result.agents));
for i = 1:length(result.agents)
    tasks_str = num2str(result.agents(i).task_sequence);
    time_hours = result.agents(i).total_time;
    fprintf('   %s → [%s]  时间: %.2f 小时\n', ...
        result.agents(i).machine_id, tasks_str, time_hours);
end
disp('========================================');