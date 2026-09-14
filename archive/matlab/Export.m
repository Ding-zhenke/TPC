
function [SPara_S11_OUT,SPara_S12_OUT] = Export(basePath,mws,n_count,iter_count)
%%%Author: Vapine ZH

try
%%%Date: 2023-09-27

SelectTreeItem = invoke(mws,'SelectTreeItem','1D Results\S-Parameters\S1,1');
plot1D = invoke(mws, 'Plot1D');
invoke(plot1D, 'PlotView', 'magnituded');%%请修改此处的导出格式

FileName_1 = strcat('S11_', num2str(n_count), '.txt');
fullPath_1 = fullfile(basePath,num2str(iter_count), FileName_1);

ASCIIExport = invoke(mws,'ASCIIExport');
invoke(ASCIIExport,'Reset');
invoke(ASCIIExport,'FileName',fullPath_1);
invoke(ASCIIExport,'Execute');

FileName_2 = strcat('S12_',num2str(n_count), '.txt');
fullPath_2 = fullfile(basePath,num2str(iter_count), FileName_2);

Item='1D Results\S-Parameters\S1,2';
SelectTreeItem = invoke(mws,'SelectTreeItem','1D Results\S-Parameters\S2,1');
plot1D = invoke(mws, 'Plot1D');
invoke(plot1D, 'PlotView', 'magnitudedB');%%请修改此处的导出格式

ASCIIExport = invoke(mws,'ASCIIExport');
invoke(ASCIIExport,'Reset');
invoke(ASCIIExport,'FileName',fullPath_2);
invoke(ASCIIExport,'Execute');
%{
%/invoke(plot1D, 'PlotView', 'Imaginary');
ASCIIExport = invoke(mws, 'ASCIIExport');
invoke(ASCIIExport, 'Reset');
invoke(ASCIIExport, 'FileName', 'D:xxx\S11i.txt');
invoke(ASCIIExport, 'Execute');

%}
 

SPara_S11_OUT=readmatrix(fullPath_1);
SPara_S12_OUT=readmatrix(fullPath_2);




%{
 合并数据

FileName_3 = strcat('combined_data',num2str(nn) ,'.txt');
fullPath_3 = fullfile(basePath,num2str(cc), FileName_3);

% 保存到新文件
save(fullPath_3, 'combined_data', '-ascii');
%}

catch
    SPara_S11_OUT=zeros(1002,1);
    SPara_S12_OUT=zeros(1002,1);
    fprintf('第%d个个体的S参数导出错误！已用0代替并继续运行\n',n_count);

end
end