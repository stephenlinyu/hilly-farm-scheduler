

function PlotAssignments(model, sol, figureID)

% Set plotting parameters
figure(figureID);

offset = (model.XMAX - model.XMIN)/100; 

Cmap   = colormap(lines);

% linS = {'-','-.','--',':'};

m_tasks = model.tasks;

% Plot tasks
hold on;
for m = 1:length(m_tasks)
    plot(m_tasks(m).x + [0 0], m_tasks(m).y + [0 0],'square','color',Cmap(m_tasks(m).id,:),'LineWidth',5);
%     text(m_tasks(m).x+offset, m_tasks(m).y+offset, 0.1, ['T' num2str(m)]);
    text(m_tasks(m).x+offset, m_tasks(m).y+offset,  ['T' num2str(m)]); % 修改后
    % num_req = m_tasks(m).req;
    % text(m_tasks(m).x-offset, m_tasks(m).y-offset, 0.1, ['(' num2str(num_req) ')']);
end

% Plot agents
for n=1:length(model.agents)

    plot(model.agents(n).x, model.agents(n).y, 'o','color',Cmap(model.agents(n).id,:),'MarkerSize',10,'MarkerFaceColor',Cmap(model.agents(n).id,:));

    text(model.agents(n).x+offset, model.agents(n).y+offset, ['A' num2str(n)]);

    % Check if path has something in it
    if(~isempty(sol.agents(n).task))

        taskPrev = lookupTask(model.tasks, sol.agents(n).task(1)); % get the task information

        X = [model.agents(n).x, taskPrev.x];
        Y = [model.agents(n).y, taskPrev.y];
%         Z = zeros(length(X));
%       Z = [0, taskPrev.start]; % 修改后

%         plot(X,Y,'linestyle',linS{mod(n-1, length(linS)) + 1},'color',Cmap(model.agents(n).id,:),'LineWidth',2);
        plot(X,Y,'--','color',Cmap(model.agents(n).id,:),'LineWidth',2);
        % plot3(X(end)+[0 0], Y(end)+[0 0], Z(end)+[0 0], '^','color',Cmap(model.agents(n).id,:),'MarkerSize',10,'MarkerFaceColor',Cmap(model.tasks(n).id+5,:));
        text(model.agents(n).x+offset, model.agents(n).y+offset,  ['A' num2str(n)]);

        for m = 2:length(sol.agents(n).task)
            if( ~isempty(sol.agents(n).task(m)) && m > 1 )

                taskNext = lookupTask(model.tasks, sol.agents(n).task(m));
                X = [taskPrev.x, taskNext.x];
                Y = [taskPrev.y, taskNext.y];
%                 Z = zeros(length(X)); % 修改后
%                Z = [taskPrev.start, taskNext.start];

                plot(X,Y,'color',Cmap(model.agents(n).id,:),'LineWidth',2);

                % plot3(X(end)+[0 0], Y(end)+[0 0], Z(end)+[0 0], '^','color',Cmap(model.agents(n).id,:),'MarkerSize',10,'MarkerFaceColor',Cmap(model.tasks(n).id+5,:));

                taskPrev = taskNext;

            else
                break;
            end
        end

        X = [taskPrev.x, model.agents(n).x];
        Y = [taskPrev.y, model.agents(n).y];
%         Z = zeros(length(X));
%          Z = [taskPrev.start, 0]; % 修改后

        plot(X,Y,'color',Cmap(model.agents(n).id,:),'LineWidth',2);
    end
end

% legend([agent_quad, agent_car, tasks_track, tasks_rescue], {'Quadrotors', 'Cars', 'Tracking tasks', 'Rescue tasks'}, 'Location', 'southwest');
hold off;
title('Agent Paths')
xlabel('X');
ylabel('Y');
% zlabel('Time');
grid on;

return

function task = lookupTask(tasks, taskID)

    for mi=1:length(tasks)
        if(tasks(mi).id == taskID)
            task = tasks(mi);
            return;
        end
    end
    
    task = [];
    disp(['Task with index=' num2str(taskID) ' not found'])

return

end

end

% function PlotAssignments(model, sol, figureID)
%     % Set plotting parameters
%     figure(figureID);
% 
%     % Grid size for the map
%     grid_size = 25; % 25x20 grid cells
% 
%     % Define the map based on the world boundaries
%     map = zeros(grid_size, 20); % Initialize an empty map
% 
%     % Define the types of grid cells
%     FREE = 0;         % Free space
%     FULL_OBSTACLE = 1;% Full obstacle
%     ROAD = 2;         % Road
%     STAIRCASE = 3;    % Staircase
%     TASK = 4;         % Task point
%     AGENT = 5;        % Agent position
% 
%     % Fill the map with FREE spaces
%     hold on;
%     for i = 1:grid_size
%         for j = 1:20
%             switch map(i, j)
%                 case FREE
%                     color = [1, 1, 1]; % White for free space
%                 case FULL_OBSTACLE
%                     color = [0, 0, 0]; % Black for obstacles
%                 case ROAD
%                     color = [0, 0, 1]; % Blue for roads
%                 case STAIRCASE
%                     color = [1, 0, 0]; % Red for staircases
%                 case TASK
%                     color = [0, 1, 0]; % Green for tasks
%                 case AGENT
%                     color = [1, 0.5, 0]; % Orange for agents
%             end
%             rectangle('Position', [j-1, grid_size-i, 1, 1], 'FaceColor', color, 'EdgeColor', 'k');
%         end
%     end
% 
%     % Plot tasks
%     for m = 1:length(model.tasks)
%         task = model.tasks(m);
%         x_grid = round((task.x - model.XMIN) / (model.XMAX - model.XMIN) * (grid_size - 1)) + 1;
%         y_grid = grid_size - round((task.y - model.YMIN) / (model.YMAX - model.YMIN) * (20 - 1)) - 1;
%         map(y_grid, x_grid) = TASK;
%     end
% 
%     % Plot agents
%     for n=1:length(model.agents)
%         agent = model.agents(n);
%         x_grid = round((agent.x - model.XMIN) / (model.XMAX - model.XMIN) * (grid_size - 1)) + 1;
%         y_grid = grid_size - round((agent.y - model.YMIN) / (model.YMAX - model.YMIN) * (20 - 1)) - 1;
%         map(y_grid, x_grid) = AGENT; % Mark agent's starting position
%     end
% 
%     % Plot paths
%     for n=1:length(model.agents)
%         agent = model.agents(n);
%         if(~isempty(sol.agents(n).task))
%             taskPrev = lookupTask(model.tasks, sol.agents(n).task(1)); % Get the first task information
% 
%             X = [agent.x, taskPrev.x];
%             Y = [agent.y, taskPrev.y];
%             for m = 2:length(sol.agents(n).task)
%                 if(~isempty(sol.agents(n).task(m)) && m > 1)
%                     taskNext = lookupTask(model.tasks, sol.agents(n).task(m));
%                     X = [X, taskNext.x];
%                     Y = [Y, taskNext.y];
%                 end
%             end
% 
%             % Plot the path on the map
%             for k = 1:length(X)-1
%                 x1 = round((X(k) - model.XMIN) / (model.XMAX - model.XMIN) * (grid_size - 1)) + 1;
%                 y1 = grid_size - round((Y(k) - model.YMIN) / (model.YMAX - model.YMIN) * (20 - 1)) - 1;
%                 x2 = round((X(k+1) - model.XMIN) / (model.XMAX - model.XMIN) * (grid_size - 1)) + 1;
%                 y2 = grid_size - round((Y(k+1) - model.YMIN) / (model.YMAX - model.YMIN) * (20 - 1)) - 1;
%                 line([x1, x2], [y1, y2], 'Color', 'k', 'LineWidth', 1); % Draw line between tasks
%             end
%         end
%     end
% 
%     hold off;
%     axis equal;
%     xlim([0, 20]);
%     ylim([0, grid_size]);
%     xlabel('X');
%     ylabel('Y');
%     title('Task Assignment and Paths on Grid Map');
%     return
% 
% function task = lookupTask(tasks, taskID)
%     for mi=1:length(tasks)
%         if(tasks(mi).id == taskID)
%             task = tasks(mi);
%             return;
%         end
%     end
%     task = [];
%     disp(['Task with index=' num2str(taskID) ' not found'])
%     return
% end
% end