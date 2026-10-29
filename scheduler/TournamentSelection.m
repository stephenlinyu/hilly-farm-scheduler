%
% Copyright (c) 2015, Mostapha Kalami Heris & Yarpiz (www.yarpiz.com)
% All rights reserved. Please read the "LICENSE" file for license terms.
%
% Project Code: YPEA101
% Project Title: Implementation of Real-Coded Genetic Algorithm in MATLAB
% Publisher: Yarpiz (www.yarpiz.com)
% 
% Developer: Mostapha Kalami Heris (Member of Yarpiz Team)
% 
% Cite as:
% Mostapha Kalami Heris, Binary and Real-Coded Genetic Algorithms in MATLAB (URL: https://yarpiz.com/23/ypea101-genetic-algorithms), Yarpiz, 2015.
% 
% Contact Info: sm.kalami@gmail.com, info@yarpiz.com
%

function i = TournamentSelection(pop, m)

    nPop = numel(pop);

    S = randsample(nPop, m); % return S as a colum vector of m value sampled uniformly
                             % at random from the intergers 1:nPop
    
    spop = pop(S);
    
    scosts = [spop.Cost];
    
    [~, j] = min(scosts);
    
    i = S(j); % return index of winner

end