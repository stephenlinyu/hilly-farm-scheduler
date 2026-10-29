% Create model

function model = CreateModel()
    %---------------------------------------------------------------------%
    % Initialize global variables
    %---------------------------------------------------------------------%
    
    WORLD.CLR  = rand(100,3);
    
    WORLD.XMIN = 0;
    WORLD.XMAX = 10.0;
    WORLD.YMIN = 0;
    WORLD.YMAX = 10.0;

    WORLD.MAX_DISTANCE = sqrt((WORLD.XMAX - WORLD.XMIN)^2 + ...
                              (WORLD.YMAX - WORLD.YMIN)^2);
     
    %---------------------------------------------------------------------%
    % Define agents and tasks
    %---------------------------------------------------------------------%
    
    % Initialize possible agent fields
    agent_default.id    = 0;
    agent_default.clr = [];
    agent_default.nom_vel = 0;
    agent_default.vel_task= 0;
    agent_default.wide    = 0;
    agent_default.w       = 0;
    agent_default.tturn   = 0;
    agent_default.fuel    = 0;
    agent_default.fueltask= 0;
    agent_default.x       = 0;
    agent_default.y       = 0;
    agent_default.depot_id = 1;  % 新增：所属车库ID
    
    % Initialize possible task fields
    task_default.id       = 0;
    task_default.kuan     = 0;
    task_default.chang    = 0;
    task_default.S        = 0;
    task_default.duration = 0;
    task_default.x        = 0;
    task_default.y        = 0;
    task_default.h        = 0;   % 新增：海拔高度 (m)
    
    % List agent types 
    AGENT_TYPES.CAR1   = 1;
    AGENT_TYPES.CAR2   = 2;
    AGENT_TYPES.CAR3   = 3;
    
    % List task types
    TASK_TYPES.TRACK   = 1;
    
    % Create some default agents
    % CAR1
    agent_car1         = agent_default;
    agent_car1.type    = AGENT_TYPES.CAR1;
    agent_car1.nom_vel = 4;
    agent_car1.vel_task= 2;
    agent_car1.wide    = 6.9;
    agent_car1.w       = 7000;
    agent_car1.tturn   = 0.004;
    agent_car1.fuel    = 1;
    agent_car1.fueltask= 2;
    
    % CAR2
    agent_car2         = agent_default;
    agent_car2.type    = AGENT_TYPES.CAR2;
    agent_car2.nom_vel = 10;
    agent_car2.vel_task= 5;
    agent_car2.wide    = 5.5;
    agent_car2.w       = 3000;
    agent_car2.tturn   = 0.003;
    agent_car2.fuel    = 2.5;
    agent_car2.fueltask= 5;
    
    % CAR3
    agent_car3         = agent_default;
    agent_car3.type    = AGENT_TYPES.CAR3;
    agent_car3.nom_vel = 5;
    agent_car3.vel_task= 3;
    agent_car3.wide    = 3.7;
    agent_car3.w       = 4000;
    agent_car3.tturn   = 0.002;
    agent_car3.fuel    = 2;
    agent_car3.fueltask= 4;
    
    % Create some default tasks
    task_track          = task_default;
    task_track.type     = TASK_TYPES.TRACK;
   
    %---------------------------------------------------------------------%
    % Define sample scenario
    %---------------------------------------------------------------------%
    
    N = 8;      % number of agents
    M = 30;     % number of tasks
    
    % ========== 定义车库 ==========
    depots = [];
    depots(1).x = 3;
    depots(1).y = 3;
    depots(1).h = 300;   % 海拔 (m)
    
    depots(2).x = 7;
    depots(2).y = 3;
    depots(2).h = 450;   % 海拔 (m)
    
    % ========== 创建 agents ==========
    for n = 1:N
        agents(n) = agent_car2;
        
        % 前3台农机从车库1出发，后3台从车库2出发
        if n <= 3
            agents(n).x = depots(1).x;
            agents(n).y = depots(1).y;
            agents(n).depot_id = 1;
        else
            agents(n).x = depots(2).x;
            agents(n).y = depots(2).y;
            agents(n).depot_id = 2;
        end
        
        agents(n).id   = n;
        agents(n).clr  = WORLD.CLR(n,:);
    end
    
    % ========== 创建 tasks（40个，含海拔） ==========
    fixed_task_data = [
        0   0   245 750;
        2   1   380 770;
        0.5 3   315 1200;
        1.5 4   420 960;
        4   4   270 1064;
        5   2   355 1100;
        4   1   490 1000;
        0   7   225 600;
        1   6   385 700;
        3   5   440 400;
        4   6   410 1080;
        1   8   290 1026;
        2   10  470 975;
        4   9   335 966;
        6   1   505 1056;
        8   0   275 1032;
        10  2   395 1107;
        9   4   450 980;
        6   2   305 1200;
        5.5 4   520 1125;
        6   5   365 1034;
        8   4   430 576;
        6   7   250 969;
        5   6   395 950;
        7   5   345 1173;
        8   6   465 1040;
        6   8   290 700;
        7   10  535 648;
        8   9   310 529;
        10  7   475 1044;
        0.2 1.5 520 1250;
        3   2   265 825;
        0.5 10  445 1400;
        2.8 7.5 305 1430;
        5.5 10  480 1800;
        7.5 7.5 330 1020;
        9.5 9.5 410 972;
        9.7 5   360 1140;
        10  0.1 495 800;
        8.2 1.5 385 900;
    ];
    
    for m = 1:M
        tasks(m) = task_track;
        tasks(m).id = m;
        tasks(m).x = fixed_task_data(m, 1);
        tasks(m).y = fixed_task_data(m, 2);
        tasks(m).h = fixed_task_data(m, 3);  % 海拔 (m)
        tasks(m).S = fixed_task_data(m, 4);  % 作业面积 (m?)
    end
    
    % ========== 构建 model ==========
    model = WORLD;
    model.tasks = tasks;
    model.agents = agents;
    model.depots = depots;
    model.N = N;
    model.M = M;
    
model.mu_u = 10;          % 上坡能耗敏感系数（无量纲）
model.mu_d = 2;          % 下坡能耗敏感系数
model.v_max = 30;          % 最大安全速度 (km/h)，根据实际情况设定

    
end
