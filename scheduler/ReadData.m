function model = ReadData()
    % ============================================================
    % 读取 Python 导出的 CSV 文件
    % 兼容 MATLAB R2016a
    % ============================================================
    
    % 获取当前脚本所在目录
    scriptPath = fileparts(mfilename('fullpath'));
    
    % 检查 CSV 文件是否存在
    machineFile = fullfile(scriptPath, 'machines.csv');
    fieldFile = fullfile(scriptPath, 'fields.csv');
    
    if ~exist(machineFile, 'file')
        error('? 未找到 machines.csv，请先在网页中点击"智能调度"导出数据');
    end
    if ~exist(fieldFile, 'file')
        error('? 未找到 fields.csv，请先在网页中点击"智能调度"导出数据');
    end
    
    % 读取 machines.csv
    fid = fopen(machineFile, 'r');
    header = fgetl(fid);
    C = textscan(fid, '%s %f %f %f', 'Delimiter', ',');
    fclose(fid);
    
    machine_ids = C{1};
    machine_x = C{2};
    machine_y = C{3};
    machine_h = C{4};
    N = length(machine_ids);
    
    % 读取 fields.csv
    fid = fopen(fieldFile, 'r');
    header = fgetl(fid);
    C = textscan(fid, '%s %f %f %f %f', 'Delimiter', ',');
    fclose(fid);
    
    field_ids = C{1};
    field_x = C{2};
    field_y = C{3};
    field_h = C{4};
    field_S = C{5};
    M = length(field_ids);
    
    % ===== 构建 model =====
    model.N = N;
    model.M = M;
    
    % 坐标范围
    all_x = [machine_x; field_x];
    all_y = [machine_y; field_y];
    model.XMIN = min(all_x) - 0.1;
    model.XMAX = max(all_x) + 0.1;
    model.YMIN = min(all_y) - 0.1;
    model.YMAX = max(all_y) + 0.1;
    
    % ===== 创建车库（depots） =====
    % 简单：使用农机的位置作为车库位置
    if N >= 2
        model.depots(1).x = machine_x(1);
        model.depots(1).y = machine_y(1);
        model.depots(1).h = machine_h(1);
        model.depots(2).x = machine_x(end);
        model.depots(2).y = machine_y(end);
        model.depots(2).h = machine_h(end);
    else
        model.depots(1).x = machine_x(1);
        model.depots(1).y = machine_y(1);
        model.depots(1).h = machine_h(1);
        model.depots(2).x = machine_x(1) + 0.1;
        model.depots(2).y = machine_y(1) + 0.1;
        model.depots(2).h = machine_h(1) + 10;
    end
    
    % 构建 agents
    for i = 1:N
        model.agents(i).id = i;
        model.agents(i).x = machine_x(i);
        model.agents(i).y = machine_y(i);
        model.agents(i).h = machine_h(i);
        model.agents(i).machine_id = machine_ids{i};
        % 默认参数（匹配 CostFunction 要求）
        model.agents(i).nom_vel = 4;
        model.agents(i).fuel = 0.06;
        model.agents(i).fueltask = 2.0;
        model.agents(i).w = 7000;
        model.agents(i).clr = rand(1,3);
        % 分配车库：前一半去车库1，后一半去车库2
        if i <= floor(N/2)
            model.agents(i).depot_id = 1;
        else
            model.agents(i).depot_id = 2;
        end
    end
    
    % 构建 tasks
    for j = 1:M
        model.tasks(j).id = j;
        model.tasks(j).x = field_x(j);
        model.tasks(j).y = field_y(j);
        model.tasks(j).h = field_h(j);
        model.tasks(j).S = field_S(j);
        model.tasks(j).farmland_id = field_ids{j};
    end
    
    % 算法参数
    model.mu_u = 10;
    model.mu_d = 2;
    model.v_max = 30;
    
    fprintf('? 已读取 %d 台农机和 %d 块农田\n', N, M);
end