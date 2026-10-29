

function i = RouletteWheelSelection(P)   % 函数的输出i是一个整数，表示被选中个体的索引

    r = rand;  % 0-1
    
    c = cumsum(P);  % 概率累计和 若p=[0.1 0.2 0.3 0.4.] 则c=[0.1 0.3 0.6 1.0]；若r=0.2,则返回索引i=2
    
    i = find(r <= c, 1, 'first'); % 只返回第一个小于等于c 的元素的索引,1表示一个元素，first表示第一个；
  
end