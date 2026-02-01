%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%变量初始化%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%


%%路径名称相关变量
basePath = 'D:\GX\';  % 路径，文件夹最后需要加一个\
FileName_CST='FILTER.cst';%待优化的原始文件名称


%%遗传算法相关变量
GA.StartFlag=0;     %断点标识位，表示是否要基于上一次的结果继续运算。1表示是，0表示否。继续运算将完全覆盖此前结果，请做好备份。
GA.Gen_No=4; % 种群数量
GA.Gen_Length=10;   % 基因长度，优化区域的X向像素点个数
GA.Gen_Width=14;    % 基因宽度,优化区域的Y向像素点个数
GA.mut_prob = 0.3; % 变异概率
GA.cross_prob = 0.8; % 交叉概率


%%建模相关变量
BrickSet.Material='Gold';
BrickSet.X_Min=0.09;      % X方向起始位置
BrickSet.Y_Min=-0.5;      % Y方向起始位置
BrickSet.Z_Min=-0.025;
BrickSet.Z_Max=-0.026;
BrickSet.Minsize=0.02;  %最小像素长宽  单位毫米


%%镜像相关变量
MirrorSet.Flag=1;    %镜像标识位。如需优化区域对称设计置为1，否则设置为0.
     MirrorSet.X=1; %镜像方向
     MirrorSet.Y=0;
     MirrorSet.Z=0; 
     MirrorSet.CenterX=0;%镜像中心坐标
     MirrorSet.CenterY=0;
     MirrorSet.CenterZ=0;



%%平移相关变量    
TranslateSet.Flag=1; %平移标识位。如需优化区域平移设计置为1，否则设置为0.
     TranslateSet.X=1;
     TranslateSet.Y=0;
     TranslateSet.Z=0;   

%%下述函数用于给定标准S参数值（即已确定了一个目标S参数结果，则使用该函数给入）
%%CST存在BUG，即使相同采样点数，多次仿真仍然可能产生1-2个采样点数量差异（比如规定采样点数1001，但仿真出来可能有1000-1002个计算结果）
% 这样的BUG导入MATLAB后可能存在矩阵长度不对齐的BUG，因此在目标函数计算时请对齐（）
%{



FileName_Standard_11='S11.txt' %给定S11文件名称
fullPath_Standard_11 = fullfile(basePath,FileName_Standard_11);
FileName_Standard_12='S12.txt' %给定S11文件名称
fullPath_Standard_12 = fullfile(basePath,FileName_Standard_12);
S11_Standard=readmatrix(fullPath_Standard_11);
S11_Standard=readmatrix(fullPath_Standard_12);


%}



r = rand; %适应度阈值
tol = 1e-6; % 停止条件

max_iter = 100; % 最大迭代次数
fi=zeros(GA.Gen_No,max_iter); 


%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%初始种群生成%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

pop = rand(GA.Gen_Length,GA.Gen_Width,GA.Gen_No); % 种群基因
for nn=1:GA.Gen_No
    for ii=1:GA.Gen_Length
        for jj=1:GA.Gen_Width
            if pop(ii,jj,nn)>=0.2
               pop(ii,jj,nn)=1;
            else
               pop(ii,jj,nn)=0;
            end
        end
    end
end
FullPath_Break = fullfile(basePath,'Break.txt');
all_pop = zeros(GA.Gen_Length,GA.Gen_Width,GA.Gen_No,max_iter); % 新种群基因
all_prob= zeros(GA.Gen_No,max_iter); % 新种群基因

try
    if exist(FullPath_Break,'file') && GA.StartFlag==1
        StartPoint=readmatrix(FullPath_Break);
        for nn=1:GA.Gen_No
            FileName_Pop = strcat('Iter_', num2str(iter_count), '_POP.txt');
            FullPath_Pop = fullfile(basePath,'StartPoint\', num2str(nn), FileName_Pop);
            pop(:,:,nn)=readmatrix(FullPath_Pop);
        end
    end
catch
    fprintf('未检测到此前迭代信息或迭代信息无法正确识别，程序将重新初始化种群\n');
end

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%正式开始运算%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

for iter_count = 1:max_iter
    fprintf('正在进行第%d次运算...\n',iter_count);
    f =F_SIMULATE(FileName_CST,basePath,pop,GA,BrickSet,MirrorSet,TranslateSet,iter_count);

    for nn=1:GA.Gen_No
        fi(nn,iter_count)=f(nn,1);
        if min(f) < tol % 满足停止条件
            break;
        end
    end
    prob = f / sum(f); % 计算每个个体的选择概率
    cum_prob = cumsum(prob); % 计算累计概率
    all_prob(:,iter_count)=prob(:,1);
    probs=sort(prob);
    fprintf('本轮运算中最优个体的适应度是%d\n',probs(1));
    
    FAR=probs(nn-2);
    max_n=find(prob>=FAR);
    BET=probs(2);
    min_n=find(prob<=BET);


    for up=1:3
        aup=max_n(up);
        bup=min_n(up);
        pop(:,:,aup)=pop(:,:,bup);
    end

    for m = 1:2:GA.Gen_No
        if rand < GA.cross_prob % 判断是否进行交叉
            k_i = randi(GA.Gen_Length-1); % 生成随机交叉点
            k_j = randi(GA.Gen_Width-1); % 生成随机交叉点
            cross_sta=zeros(GA.Gen_Length,GA.Gen_Width);
            cross_sta(k_i+1:GA.Gen_Length,k_j+1:GA.Gen_Width)=pop(k_i+1:GA.Gen_Length,k_j+1:GA.Gen_Width,m);
            pop(k_i+1:GA.Gen_Length,k_j+1:GA.Gen_Width,m) = pop(k_i+1:GA.Gen_Length,k_j+1:GA.Gen_Width,m+1); % 交叉操作
            pop(k_i+1:GA.Gen_Length,k_j+1:GA.Gen_Width,m+1)= cross_sta(k_i+1:GA.Gen_Length,k_j+1:GA.Gen_Width);
        end
    end

    for m = 1:GA.Gen_No
        if rand < GA.mut_prob % 判断是否进行变 异
            k_i = randi(GA.Gen_Length-1); % 生成随机交叉点
            k_j = randi(GA.Gen_Width-1); % 生成随机交叉点
            pop(k_i,k_j,m) =1 - pop(k_i,k_j,m); % 变异操作
        end
    end

    all_pop(:,:,:,iter_count)=pop(:,:,:); % 新种群基因

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%结果导出与后处理%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%    
    for nn=1:GA.Gen_No
        FileName_Pop = strcat('Iter_', num2str(iter_count), '_POP.txt');
        Road_Pop=fullfile(basePath,num2str(iter_count), num2str(nn));
        FullPath_Pop = fullfile(basePath,num2str(iter_count), num2str(nn), FileName_Pop);
        if ~exist(Road_Pop,'dir')
        mkdir(Road_Pop);
        end
        writematrix(pop(:,:,nn),FullPath_Pop,'Delimiter','tab','writemode','overwrite')
    end

    writematrix(iter_count,FullPath_Break,'Delimiter','tab','writemode','overwrite')

end
