function [F_out] = F_SIMULATE(FileName_CST,basePath,pop,GA,BrickSet,MirrorSet,TranslateSet,iter_count)
FileName_F = strcat('Iter_', num2str(iter_count), '_F.txt');
fullPath_F = fullfile(basePath,num2str(iter_count), FileName_F);
F_out=zeros(GA.Gen_No,1);
f_count=0;
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%检测此前是否已有计算好的结果%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
for n_count=1:GA.Gen_No

    FileName_EXIST_11= strcat('S11_', num2str(n_count), '.txt');
    fullPath_EXIST_11 = fullfile(basePath,num2str(iter_count), FileName_EXIST_11);

    FileName_EXIST_12= strcat('S12_', num2str(n_count), '.txt');
    fullPath_EXIST_12 = fullfile(basePath,num2str(iter_count), FileName_EXIST_12);

    if exist(fullPath_EXIST_11,'file') && exist(fullPath_EXIST_12,'file')
        SPara_S11=readmatrix(fullPath_EXIST_11);
        SPara_S12=readmatrix(fullPath_EXIST_12);
    else 
        fullPath_FolderName = fullfile(basePath,num2str(iter_count));
        if ~exist(fullPath_FolderName,'dir')
        mkdir(fullPath_FolderName);
        end
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%开始执行仿真%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
        [SPara_S11,SPara_S12] = Slover(FileName_CST,basePath,pop,n_count,GA,BrickSet,MirrorSet,TranslateSet,iter_count);
    end

    S11=zeros(1002,5);
    S12=zeros(1002,5);
    for fre=1:1002
        S11(fre,1)=SPara_S11(fre,1);
        S12(fre,1)=SPara_S12(fre,1);
    end


    Sample_MIN=200;   %计算目标函数的起始采样点数
    Sample_MAX=1000;     %计算目标函数的终止采样点数


%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%目标函数计算%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    for ii=Sample_MIN:Sample_MAX

        A1=(SPara_S11(ii,1)-4)^2;

        A2=(SPara_S12(ii,1)-2)^2;

        f_count=f_count+0.5*A1+0.5*A2;

        clear A1 A2

    end
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%目标函数导出%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%


    F_out(n_count,1)=f_count; 
    f_count=0;
end

writematrix(F_out,fullPath_F,'Delimiter','tab','writemode','overwrite')
end