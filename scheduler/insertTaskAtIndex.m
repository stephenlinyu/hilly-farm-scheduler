
function taskList = insertTaskAtIndex(taskList, task, index)
    % 这个辅助函数用于在指定位置插入任务
    taskList = [taskList(1:index-1), task, taskList(index:end)];
end