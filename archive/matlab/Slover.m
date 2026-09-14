function [SPara_S11_OUT,SPara_S12_OUT] = Slover(FileName_CST,basePath,pop,n_count,GA,BrickSet,MirrorSet,TranslateSet,iter_count)

%为调试写的定义，包装后上述删除


% 基础路径部分('');


% 动态生成文件夹和文件名

FileName_CSTNEW = strcat('Iter_',num2str(iter_count),'_Number_',num2str(n_count),'.cst');
% 拼接完整路径
FullPath_CST = fullfile(basePath,FileName_CST);


%originfilename=('D:\Topology\DSG.cst'); 

cst=actxserver('CSTStudio.application');  %%首先载入CST应用控件


%mws=invoke(cst,'NewMWS');  %新建一个MWS项目
mws = invoke(cst,'OpenFile', FullPath_CST);
app=invoke(mws,'GetApplicationName');  %%获取当前应用名称
ver=invoke(mws,'GetApplicationVersion');%获取当前应用版本号

%project = cst.GetObject('Project');
%invoke(mws,'FileNew');  %%新建一个CST文档
%filename=['D:\Topology\COUPLERPCB7.cst'];  %%新建的CST文件名字
%invoke(mws,'OpenFile',originfilename);
invoke(mws,'DeleteResults');  %%删除之前的结果


%{
定义单位
units=invoke(mws,'Units');
invoke(units,'Geometry','mm');
invoke(units,'Frequency','GHz');
invoke(units, 'Time', 'ns');
invoke(units, 'TemperatureUnit', 'kelvin');
release(units);
%}
%%使Bounding Box显示
plot=invoke(mws,'Plot');
invoke(plot,'DrawBox','True');
%%使Bounding Box显示结束


%{
背景材料设置
background = invoke(mws, 'Background');
invoke(background, 'ResetBackground');
invoke(background, 'Type', 'Normal');
release(background);
%}



%{
定义边界条件
boundary=invoke(mws,'Boundary');
invoke(boundary,'Xmin','unit cell');
invoke(boundary,'Xmax','unit cell');
invoke(boundary,'Ymin','unit cell');
invoke(boundary,'Ymax','unit cell');
invoke(boundary,'Zmin','electric');
invoke(boundary,'Zmax','expanded open');
invoke(boundary,'SetPeriodicBoundaryAnglesDirection','inward');
release(boundary);
%}

%%定义Floquet边界条件
%floquetport=invoke(mws,'FloquetPort');
%invoke(floquetport,'Reset');
%invoke(floquetport,'Port','Zmax');
%invoke(floquetport,'SetNumberOfModesConsidered',2);
%invoke(floquetport,'SetDistanceToReferencePlane',-lamda/4);
%invoke(floquetport,'SetUseCircularPolarization','False');
%release(floquetport);

%{
工作频率设置
Frequency=[0,18];  %%工作频率设置(GHz)
solver=invoke(mws,'Solver');
invoke(solver,'FrequencyRange',100,160);
release(solver);
%}
%%设置网格
mesh=invoke(mws,'Mesh');
invoke(mesh,'SetCreator','High Frequency');
release(mesh);


%{
设置频域仿真求解器
fdsolver=invoke(mws,'FDSolver');
invoke(fdsolver,'Reset');
invoke(fdsolver,'SetMethod','Tetrahedral','General purpose');
invoke(fdsolver,'OrderTet','Second');
invoke(fdsolver,'OrderSrf','First');
invoke(fdsolver,'Stimulation','Zmax','All');
invoke(fdsolver,'ResetExcitationList');
release(fdsolver);
%}
%{
定义材料
material=invoke(mws,'Material');
invoke(material,'Reset');
invoke(material,'Name','FR-4 (lossy)'); 
invoke(material,'Folder',''); 
invoke(material,'FrqType','all');
invoke(material,'Type','Normal');
invoke(material,'SetMaterialUnit','GHz','mm');
invoke(material,'Epsilon','4.3');
invoke(material,'Mu','1.0');
invoke(material,'Kappa','0.0');
invoke(material,'TanD','0.025');
invoke(material,'TanDFreq','9.0');
invoke(material,'TanDGiven','True');
invoke(material,'TanDModel','ConstTanD');
invoke(material,'Create');
release(material);
%}
%%定义新的组件
component=invoke(mws,'Component');
invoke(component,'New','component1');



namecount=0;
    for ii=1:GA.Gen_Length
        for jj =1:GA.Gen_Width
            if pop(ii,jj,n_count)==1
            namecount=namecount+1;
            brick=invoke(mws,'Brick');
            invoke(brick,'Reset');
            invoke(brick,'Name',namecount);
            invoke(brick,'Component','TopoOpti');
            invoke(brick,'Material',BrickSet.Material);
 
            invoke(brick,'Xrange',BrickSet.X_Min+(ii-1)*BrickSet.Minsize,BrickSet.X_Min+ii*BrickSet.Minsize);

            invoke(brick,'Yrange',BrickSet.Y_Min+(jj-1)*BrickSet.Minsize,BrickSet.Y_Min+jj*BrickSet.Minsize);
            
            invoke(brick,'Zrange',BrickSet.Z_Min,BrickSet.Z_Max);
            invoke(brick,'Create');
            release(brick);           
            end
        end
    end
if TranslateSet.Flag==1
        Transform=invoke(mws,'Transform');
        invoke(Transform,'Reset');
        invoke(Transform,'Name','TopoOpti');
        invoke(Transform,'Vector',TranslateSet.X,TranslateSet.Y,TranslateSet.Z);%%控制平移方向和位置
        invoke(Transform,'UsePickedPoints','False');
        invoke(Transform,'InvertPickedPoints','False');
        invoke(Transform,'MultipleObjects','True');
        invoke(Transform,'GroupObjects','False');
        invoke(Transform,'Repetitions',1);
        invoke(Transform,'MultipleSelection','False');
        invoke(Transform,'AutoDestination','True');     
        invoke(Transform,'Transform','Shape','Translate');     
        release(Transform);
end
if MirrorSet.Flag==1
    Transform=invoke(mws,'Transform');
     invoke(Transform,'Reset');
     invoke(Transform,'Name','TopoOpti');
     invoke(Transform,'Origin','Free');
     invoke(Transform,'Center',MirrorSet.CenterX,MirrorSet.CenterY,MirrorSet.CenterZ);
     invoke(Transform,'PlaneNormal',MirrorSet.X,MirrorSet.Y,MirrorSet.Z);
     invoke(Transform,'MultipleObjects','True');
     invoke(Transform,'GroupObjects','False');
     invoke(Transform,'Repetitions',1);
     invoke(Transform,'MultipleSelection','False');
     invoke(Transform,'AutoDestination','True');     
     invoke(Transform,'Transform','Shape','Mirror');     
    release(Transform);
end
    %{
    Boolean Subtract
    solid=invoke(mws,'Solid');
    invoke(solid,'Subtract','component1:Outer_Square1','component1:Inner_Square1');
    release(solid);
    %}
invoke(mws,'SaveAs',FileName_CSTNEW,'True');

%setSolverType(mws, 'TimeDomain');
%%仿真开始



    solver = invoke(mws, 'FDSolver');
    invoke(solver, 'Start');
    
    %%保存已经仿真好的文件
    invoke(mws,'Save');
[SPara_S11_OUT,SPara_S12_OUT]=Export(basePath,mws,n_count,iter_count);


invoke(mws,'quit');


end