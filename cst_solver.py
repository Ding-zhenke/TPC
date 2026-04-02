# -*- coding: utf-8 -*-
"""
Created on Mon Oct 20 11:37:16 2025
CST 2025 电磁仿真自动化建模与求解核心类
封装CST软件的建模、材料、边界、端口、求解等自动化操作API
@author: PC
"""

import sys
import os
import numpy as np
# ensure the CST python libraries path is added correctly (use raw string)
sys.path.append(r"D:\CST2025\location\AMD64\python_cst_libraries")
import cst
import cst.interface
import cst.results

print(cst.__file__) 

class setup():
    """
    CST电磁仿真自动化操作核心类
    功能：封装CST的项目打开、建模、材料创建、参数设置、求解、端口/监视器创建等全流程操作
    依赖：CST2025 python_cst_libraries 库，需配置正确路径
    """
    def __init__(self,filename):
        """
        类的初始化函数，创建CST交互环境并打开指定CST工程文件
        :param filename: str, CST工程文件路径（相对/绝对路径均可）
        :raise FileNotFoundError: 传入的CST工程文件路径不存在时抛出
        :raise RuntimeError: 打开CST工程失败、文件非法、权限不足等情况抛出
        """
        # 初始化临时变量
        self.t=0
        # 初始化CST交互式设计环境
        self.project = cst.interface.DesignEnvironment()
        # 标准化文件路径为绝对路径并前置校验文件是否存在
        try:
            filename_abs = os.path.abspath(filename)
        except Exception:
            filename_abs = filename

        if not os.path.exists(filename_abs):
            # 文件不存在时抛出明确的异常信息
            raise FileNotFoundError(f"CST project file not found: {filename_abs}")

        try:
            # 尝试打开CST工程文件并激活为当前操作工程
            self.cst_file = self.project.open_project(filename_abs)
            self.cst_file.activate()
        except Exception as e:
            # 捕获底层异常并封装为更友好的运行时异常，附带故障排查提示
            raise RuntimeError(
                f"Failed to open the CST project '{filename_abs}'. "
                f"Underlying error: {e!s}.\n"
                f"Possible causes: file is not a valid .cst project, CST automation not available, or permissions/encoding issues."
            )
            
    def T_solver(self):
        """时域求解器配置预留接口，暂未实现功能"""
        pass
        
    def freq_limit(self,fmin,fmax):
        """
        设置CST仿真的求解频率范围
        :param fmin: float/str, 仿真起始频率值
        :param fmax: float/str, 仿真终止频率值
        """
        f1 = """
        'Set Freq
        Solver.FrequencyRange %s, %s
        """%(fmin,fmax)
        # 将频率范围配置指令写入CST操作历史并生效
        self.cst_file.model3d.add_to_history ("Freq_range" , f1)

    def new_material(self,name):
        """
        在CST工程中创建指定的预设材料，材料属性为固定最优仿真参数
        :param name: str, 材料名称，可选值：['Copper (annealed)', 'Silicon (lossy)', 'Quartz (Fused) (lossy)']
        :return: None，匹配不到材料名称时控制台打印提示信息
        """
        if name=='Copper (annealed)':
            f1="""
            With Material
            .Reset
            .Name "Copper (annealed)"
            .Folder ""
            .FrqType "static"
            .Type "Normal"
            .SetMaterialUnit "Hz", "mm"
            .Epsilon "1"
            .Mu "1.0"
            .Kappa "5.8e+007"
            .TanD "0.0"
            .TanDFreq "0.0"
            .TanDGiven "False"
            .TanDModel "ConstTanD"
            .KappaM "0"
            .TanDM "0.0"
            .TanDMFreq "0.0"
            .TanDMGiven "False"
            .TanDMModel "ConstTanD"
            .DispModelEps "None"
            .DispModelMu "None"
            .DispersiveFittingSchemeEps "Nth Order"
            .DispersiveFittingSchemeMu "Nth Order"
            .UseGeneralDispersionEps "False"
            .UseGeneralDispersionMu "False"
            .FrqType "all"
            .Type "Lossy metal"
            .SetMaterialUnit "GHz", "mm"
            .Mu "1.0"
            .Kappa "5.8e+007"
            .Rho "8930.0"
            .ThermalType "Normal"
            .ThermalConductivity "401.0"
            .SpecificHeat "390", "J/K/kg"
            .MetabolicRate "0"
            .BloodFlow "0"
            .VoxelConvection "0"
            .MechanicsType "Isotropic"
            .YoungsModulus "120"
            .PoissonsRatio "0.33"
            .ThermalExpansionRate "17"
            .Colour "1", "1", "0"
            .Wireframe "False"
            .Reflection "False"
            .Allowoutline "True"
            .Transparentoutline "False"
            .Transparency "0"
            .Create
            End With"""
        elif name=='Silicon (lossy)':
            f1="""
            With Material
            .Reset
            .Name "Silicon (lossy)"
            .Folder ""
            .FrqType "all"
            .Type "Normal"
            .SetMaterialUnit "GHz", "mm"
            .Epsilon "11.9"
            .Mu "1.0"
            .Kappa "2.5e-004"
            .TanD "0.00"
            .TanDFreq "0.0"
            .TanDGiven "False"
            .TanDModel "ConstTanD"
            .KappaM "0.0"
            .TanDM "0.0"
            .TanDMFreq "0.0"
            .TanDMGiven "False"
            .TanDMModel "ConstKappa"
            .DispModelEps "None"
            .DispModelMu "None"
            .DispersiveFittingSchemeEps "General 1st"
            .DispersiveFittingSchemeMu "General 1st"
            .UseGeneralDispersionEps "False"
            .UseGeneralDispersionMu "False"
            .Rho "2330.0"
            .ThermalType "Normal"
            .ThermalConductivity "148"
            .SpecificHeat "700", "J/K/kg"
            .SetActiveMaterial "all"
            .MechanicsType "Isotropic"
            .YoungsModulus "112"
            .PoissonsRatio "0.28"
            .ThermalExpansionRate "5.1"
            .Colour "0.94", "0.82", "0.76"
            .Wireframe "False"
            .Transparency "0"
            .Create
            End With"""
        elif name=="Quartz (Fused) (lossy)":
            f1="""With Material
     .Reset
     .Name "Quartz (Fused) (lossy)"
     .Folder ""
     .FrqType "all"
     .Type "Normal"
     .SetMaterialUnit "MHz", "mm"
     .Epsilon "3.75"
     .Mu "1.0"
     .Kappa "0.0"
     .TanD "0.0004"
     .TanDFreq "1.0"
     .TanDGiven "True"
     .TanDModel "ConstTanD"
     .KappaM "0.0"
     .TanDM "0.0"
     .TanDMFreq "0.0"
     .TanDMGiven "False"
     .TanDMModel "ConstKappa"
     .DispModelEps "None"
     .DispModelMu "None"
     .DispersiveFittingSchemeEps "General 1st"
     .DispersiveFittingSchemeMu "General 1st"
     .UseGeneralDispersionEps "False"
     .UseGeneralDispersionMu "False"
     .Rho "2200.0"
     .ThermalType "Normal"
     .ThermalConductivity "5"
     .SpecificHeat "700", "J/K/kg"
     .SetActiveMaterial "all"
     .MechanicsType "Isotropic"
     .YoungsModulus "75"
     .PoissonsRatio "0.17"
     .ThermalExpansionRate "0.5"
     .Colour "0.94", "0.82", "0.76"
     .Wireframe "False"
     .Transparency "0"
     .Create
End With
"""
        else:
            print("没有该材料，请手动添加")
        self.cst_file.model3d.add_to_history (name , f1)

    def run(self):
        """执行当前CST工程的求解器计算，提交仿真任务"""
        self.cst_file.model3d.run_solver()
    def update(self):
        """刷新当前CST工程的模型历史，使得参数修改等操作生效"""
        self.cst_file.model3d.full_history_rebuild()
    def project_open(self,filename):
        self.cst_file = self.project.open_project(filename)
        self.cst_file.activate()
        print('项目已打开并激活')
    def project_close(self):
        self.cst_file.close()
        print('项目已关闭')
    def close(self):
        """关闭当前打开的CST工程文件和设计环境，释放资源"""
        self.cst_file.close()
        self.project.close()
        
    def para(self,name,value,log_flag=0):
        """
        在CST工程中创建/修改全局仿真参数
        :param name: str, 参数名称
        :param value: float/str, 参数赋值
        :param log_flag: int, 刷新标识 0-不刷新历史 1-全量刷新工程历史使参数立即生效，默认0
        """
        # 存储参数到CST工程
        self.cst_file.model3d.StoreParameter(f"{name}",value)
        # 加载到项目历史，使得参数生效
        if log_flag==1:
            self.cst_file.model3d.full_history_rebuild()    
    def paras(self,name,value,log_flag=0):
        """
        批量创建/修改全局仿真参数
        :param paras_dict: dict, 参数字典 {参数名称: 参数值, ...}
        :param log_flag: int, 刷新标识 0-不刷新历史 1-全量刷新工程历史使参数立即生效，默认0
        """
        self.cst_file.model3d.StoreParameters(name,value)
        if log_flag==1:
            self.cst_file.model3d.full_history_rebuild()
    def expression(self,name,value):
        """
        在CST工程中创建/修改带表达式的参数（支持公式、关联其他参数）
        :param name: str, 表达式参数名称
        :param value: str, 表达式内容（如：'a*2+1', 'sqrt(b)'）
        """
        self.cst_file.model3d.RestoreParameterExpression(f"{name}",f"{value}")         
            
    def new_componet(self,name):
        """
        在CST工程中创建新的组件分组，用于模型对象归类管理
        :param name: str, 新建组件的名称
        """
        f1="""
        '  new component: %s
        Component.New "%s" 
        """%(name,name)
        self.cst_file.model3d.add_to_history ("Freq_range " , f1)
        
    def square(self,xmin,xmax,ymin,ymax,zmin,zmax,name,component='component1',material='PEC'):
        """
        创建长方体(立方体)三维实体模型
        :param xmin: float/str, X轴最小值
        :param xmax: float/str, X轴最大值
        :param ymin: float/str, Y轴最小值
        :param ymax: float/str, Y轴最大值
        :param zmin: float/str, Z轴最小值
        :param zmax: float/str, Z轴最大值
        :param name: str, 长方体模型名称
        :param component: str, 归属组件名称，默认component1
        :param material: str, 模型材料名称，默认理想导体PEC
        """
        f1 = f"""
        With Brick
            .Reset 
            .Name "{name}"
            .Component "{component}"
            .Material "{material}" 
            .Xrange "{xmin}", "{xmax}" 
            .Yrange "{ymin}", "{ymax}"
            .Zrange "{zmin}", "{zmax}"
            .Create
        End With
        """
        self.cst_file.model3d.add_to_history ("Square: "+name , f1)
        
    def cylinder(self,center,r,h,name,axis='z',component='component1',material='PEC'):
        """
        创建圆柱体(空心圆柱/圆管)三维实体模型，仅支持Z轴方向
        :param center: list, 圆柱中心点坐标 [X,Y]
        :param r: list, 半径参数 [外半径, 内半径] 内半径为0则是实心圆柱
        :param h: list, Z轴高度范围 [z起始值, z终止值]
        :param name: str, 圆柱体模型名称
        :param axis: str, 圆柱中心轴方向，仅支持z轴，默认z
        :param component: str, 归属组件名称，默认component1
        :param material: str, 模型材料名称，默认理想导体PEC
        """
        if axis=='z':
            f1=f"""
            With Cylinder 
            .Reset 
            .Name "{name}" 
            .Component "{component}" 
            .Material "{material}" 
            .OuterRadius "{r[0]}" 
            .InnerRadius "{r[1]}" 
            .Axis "z" 
            .Zrange "{h[0]}", "{h[1]}" 
            .Xcenter "{center[0]}" 
            .Ycenter "{center[1]}" 
            .Segments "0" 
            .Create 
        End With
        """
        self.cst_file.model3d.add_to_history (f"Cylinder: {name} " , f1)
        
    def triangle(self,a,h,center,theta,name,curve,material='Silicon (lossy)'):
        """
        创建正三角形棱柱三维实体模型，支持旋转+平移
        :param a: float/str, 正三角形边长
        :param h: float/str, 棱柱Z轴拉伸高度
        :param center: list, 模型最终平移中心坐标 [X,Y,Z]
        :param theta: list, 旋转角度 [X角度,Y角度,Z角度] 均为0则不旋转
        :param name: str, 三角形棱柱模型名称
        :param curve: str, 绘制三角形的曲线名称
        :param material: str, 模型材料名称，默认损耗硅 Silicon (lossy)
        """
        data=[
                [f"0",f"{a}/sqr(3)"],
                [f"-{a}/(2)",f"-{a}/2/sqr(3)"],
                [f"{a}/(2)",f"-{a}/2/sqr(3)"],
                ["0",f"{a}/sqr(3)"]
                ]
        f1=self.polyline(data,name,curve,log_flag=0)
        f2=self.extrude(f'{curve}:{name}',f'{name}',f'{h}',component='component1',material=material,log_flag=0)
        f1=f1+f2
        if theta!=[0,0,0]:
            f3=self.rotation(f'{name}',theta,component='component1',log_flag=0)
            f1=f1+f3
        f4=self.translate(f'{name}',center,component='component1',log_flag=0)
        f1=f1+f4
        self.cst_file.model3d.add_to_history (" Triangle: "+name , f1)
        
    def hexagon(self,a,h,center,theta,name,curve='curve1',component='component1',material='Silicon (lossy)'):
        """
        创建正六边形棱柱三维实体模型，支持旋转+平移
        :param a: float/str, 正六边形外接圆半径
        :param h: float/str, 棱柱Z轴拉伸高度
        :param center: list, 模型最终平移中心坐标 [X,Y,Z]
        :param theta: list, 旋转角度 [X角度,Y角度,Z角度] 均为0则不旋转
        :param name: str, 六边形棱柱模型名称
        :param curve: str, 绘制六边形的曲线名称，默认curve1
        :param component: str, 归属组件名称，默认component1
        :param material: str, 模型材料名称，默认损耗硅 Silicon (lossy)
        """
        data=[]
        for i in range(7):
            tmp=[f'({a})*cosd({i*60})',f'({a})*sind({i*60})']
            data.append(tmp)
        f1=self.polyline(data,name,log_flag=0)
        f2=self.extrude(f'{curve}:{name}',f'{name}',f'{h}',component=component,material=material,log_flag=0)
        f1=f1+f2
        if theta!=[0,0,0]:
            f3=self.rotation(f'{name}',theta,component=component,log_flag=0)
            f1=f1+f3
        f4=self.translate(f'{name}',center,component=component,log_flag=0)
        f1=f1+f4
        self.cst_file.model3d.add_to_history (" Hexagon: "+name , f1)
        
    def polyline(self,data,name='1',curve='curve1',log_flag=1):
        """
        绘制二维多边形折线/闭合轮廓，基础绘图函数
        :param data: list[list], 多边形顶点坐标集合 [[x1,y1],[x2,y2],...] 最后一点需与第一点重合实现闭合
        :param name: str, 多边形名称，默认1
        :param curve: str, 归属曲线组名称，默认curve1
        :param log_flag: int, 写入历史标识 0-仅返回指令不生效 1-写入历史并立即生效，默认1
        :return: str, CST绘图指令文本
        """
        f1=f"""
        With Polygon 
            .Reset 
            .Name "{name}" 
            .Curve "{curve}" 
            .Point "{data[0][0]}", "{data[0][1]}" 
        """
        f2="""  """
        for i in range(len(data)-1):
            f2=f2+f""".LineTo "{data[i+1][0]}", "{data[i+1][1]}" 
            """
        f3=""".Create 
        End With
        """
        f1=f1+f2+f3
        if log_flag==1:
            self.cst_file.model3d.add_to_history (" Polyline "+name , f1)
        return f1
        
    def arc(self,center,p,angle,name="arc1",curve='curve1',orientation='Counterclockwise',log_flag=1):
        """
        绘制二维圆弧曲线，基础绘图函数
        :param center: list, 圆弧圆心坐标 [X,Y]
        :param p: list, 圆弧起始点坐标 [X,Y]
        :param angle: float/str, 圆弧角度
        :param name: str, 圆弧名称，默认arc1
        :param curve: str, 归属曲线组名称，默认curve1
        :param orientation: str, 圆弧绘制方向 Counterclockwise-逆时针 Clockwise-顺时针，默认逆时针
        :param log_flag: int, 写入历史标识 0-仅返回指令不生效 1-写入历史并立即生效，默认1
        :return: str, CST绘图指令文本
        """
        f1=f"""With Arc
        .Reset 
        .Name "{name}" 
        .Curve "{curve}" 
        .Orientation "{orientation}" 
        .XCenter "{center[0]}" 
        .YCenter "{center[1]}" 
        .X1 "{p[0]}" 
        .Y1 "{p[1]}" 
        .X2 "0.15" 
        .Y2 "-0.1" 
        .Angle "{angle}" 
        .UseAngle "True" 
        .Segments "0" 
        .Create
    End With"""
        if log_flag==1:
            self.cst_file.model3d.add_to_history ("Arc "+name , f1)
        return f1
        
    def extrude(self, curve, name, thickness, component='component1', material='PEC',log_flag=1):
        """
        将二维曲线拉伸为三维实体（挤出成型），核心建模函数
        :param curve: str, 待拉伸的曲线全名 格式：curve组名:曲线名
        :param name: str, 拉伸后三维实体的名称
        :param thickness: float/str, 拉伸高度（Z轴方向）
        :param component: str, 归属组件名称，默认component1
        :param material: str, 实体材料名称，默认理想导体PEC
        :param log_flag: int, 写入历史标识 0-仅返回指令不生效 1-写入历史并立即生效，默认1
        :return: str, CST拉伸指令文本
        """
        f1=f"""
        With ExtrudeCurve
             .Reset 
             .Name "{name} "
             .Component "{component}"
             .Material "{material}"
             .Thickness "{thickness}" 
             .Twistangle "0.0" 
             .Taperangle "0.0" 
             .DeleteProfile "True" 
             .Curve "{curve}" 
             .Create
        End With
        """
        if log_flag==1:
            self.cst_file.model3d.add_to_history (name+"  extrude  " , f1)
        return f1
        
    def rotation(self,name,angle,center=['0','0','0'],repetition=1,component='component1',copy=False,unite=False,log_flag=1):
        """
        对三维实体执行旋转变换，支持复制旋转/合并旋转
        :param name: str, 待旋转的实体名称
        :param angle: list, 旋转角度 [X轴角度,Y轴角度,Z轴角度]
        :param center: list, 旋转中心点坐标 [X,Y,Z]，默认原点
        :param repetition: int, 旋转复制份数，默认1（仅旋转不复制）
        :param component: str, 实体归属组件名称，默认component1
        :param copy: bool, 是否保留原实体 True-复制旋转 False-直接旋转，默认False
        :param unite: bool, 是否合并旋转后的实体 True-合并 False-独立，默认False
        :param log_flag: int, 写入历史标识 0-仅返回指令不生效 1-写入历史并立即生效，默认1
        :return: str, CST旋转指令文本
        """
        f1=f"""With Transform 
     .Reset 
     .Name "{component}:{name}" 
     .Origin "Free" 
     .Center "{center[0]}", "{center[1]}", "{center[2]}" 
     .Angle "{angle[0]}", "{angle[1]}", "{angle[2]}" 
     .MultipleObjects "{copy}" 
     .GroupObjects "{unite}" 
     .Repetitions "{repetition}" 
     .MultipleSelection "False" 
     .AutoDestination "True" 
     .Transform "Shape", "Rotate" 
End With
"""
        if log_flag==1:
            self.cst_file.model3d.add_to_history (" roation "+name , f1)
        return f1
        
    def translate(self,name,vector,component='component1',repetitions=1,copy=False,unite=False,log_flag=1):
        """
        对三维实体执行平移变换，支持复制平移/阵列平移
        :param name: str, 待平移的实体名称
        :param vector: list, 平移矢量 [X偏移量,Y偏移量,Z偏移量]
        :param component: str, 实体归属组件名称，默认component1
        :param repetitions: int, 平移复制份数，默认1（仅平移不复制）
        :param copy: bool, 是否保留原实体 True-复制平移 False-直接平移，默认False
        :param unite: bool, 是否合并平移后的实体 True-合并 False-独立，默认False
        :param log_flag: int, 写入历史标识 0-仅返回指令不生效 1-写入历史并立即生效，默认1
        :return: str, CST平移指令文本
        """
        f1=f"""With Transform 
     .Reset 
     .Name "{component}:{name}" 
     .Vector "{vector[0]}", "{vector[1]}", "{vector[2]}" 
     .UsePickedPoints "False" 
     .InvertPickedPoints "False" 
     .MultipleObjects "{copy}" 
     .GroupObjects "{unite}" 
     .Repetitions "{repetitions}" 
     .MultipleSelection "False" 
     .AutoDestination "True" 
     .Transform "Shape", "Translate" 
End With
"""
        if log_flag==1:
            self.cst_file.model3d.add_to_history (" translate "+name , f1)
        return f1
        
    def add(self,name1,name2,component1='component1',component2='component1' ):
        """
        布尔运算-相加：将两个实体合并为一个实体，交集部分融合
        :param name1: str, 实体1名称
        :param name2: str, 实体2名称
        :param component: str, 实体归属组件名称，默认component1
        """
        f1=f"""
        Solid.Add "{component1}:{name1}", "{component2}:{name2}"
        """
        self.cst_file.model3d.add_to_history (name1+" add "+name2 , f1)
        
    def substract(self,name1,name2,component1='component1',component2='component1'):
        """
        布尔运算-相减：从实体1中减去实体2的部分，形成镂空/切槽
        :param name1: str, 被减实体名称
        :param name2: str, 裁减实体名称
        :param component: str, 实体归属组件名称，默认component1
        """
        f1=f"""
        Solid.Subtract "{component1}:{name1}", "{component2}:{name2}"
        """
        self.cst_file.model3d.add_to_history (name1+" substract "+name2 , f1)
        
    def insert(self,name1,name2,component1='component1',component2='component1'):
        """
        布尔运算-插入：在实体1中嵌入实体2，保留各自独立属性
        :param name1: str, 基础实体名称
        :param name2: str, 插入实体名称
        :param component: str, 实体归属组件名称，默认component1
        """
        f1=f"""
        Solid.Insert "{component1}:{name1}", "{component2}:{name2}"
        """
        self.cst_file.model3d.add_to_history (name1+" Insert "+name2 , f1)
        
    def intersect(self,name1,name2,component1='component1',component2='component1'):
        """
        布尔运算-相交：仅保留两个实体的重叠交集部分，其余部分删除
        :param name1: str, 实体1名称
        :param name2: str, 实体2名称
        :param component: str, 实体归属组件名称，默认component1
        """
        f1=f"""
        Solid.Intersect "{component1}:{name1}", "{component2}:{name2}"
        """
        self.cst_file.model3d.add_to_history (name1+" intersect "+name2 , f1)
        
    def mirror(self,name,center,plane,component='component1',object='Shape',copy=False,unite=False):
        """
        对实体/端口执行镜像变换，基于指定平面生成对称模型
        :param name: str, 待镜像的对象名称
        :param center: list, 镜像平面中心点坐标 [X,Y,Z]
        :param plane: list, 镜像平面法向量 [X,Y,Z] 决定镜像方向
        :param component: str, 对象归属组件名称，默认component1
        :param object: str, 镜像对象类型 Shape-三维实体 Port-端口，默认Shape
        :param copy: bool, 是否保留原对象 True-复制镜像 False-直接镜像，默认False
        :param unite: bool, 是否合并镜像后的实体 True-合并 False-独立，默认False
        """
        if object == 'Shape':
            f1=f"""With Transform 
     .Reset 
     .Name "{component}:{name}" 
     .Origin "Free" 
     .Center "{center[0]}", "{center[1]}", "{center[2]}" 
     .PlaneNormal "{plane[0]}", "{plane[1]}", "{plane[2]}" 
     .MultipleObjects "{copy}" 
     .GroupObjects "{unite}" 
     .Repetitions "1" 
     .MultipleSelection "False" 
     .Destination "" 
     .Material "" 
     .AutoDestination "True" 
     .Transform "{object}", "Mirror" 
End With
"""
        elif object == 'Port':
            f1=f"""With Transform 
        .Reset 
        .Name "{component}:{name}" 
        .Origin "Free" 
        .Center "{center[0]}", "{center[1]}", "{center[2]}" 
        .PlaneNormal "{plane[0]}", "{plane[1]}", "{plane[2]}" 
        .MultipleObjects "{copy}" 
        .GroupObjects "{unite}" 
        .Repetitions "1" 
        .MultipleSelection "False" 
        .Transform "{object}", "Mirror" 
    End With
    """
        self.cst_file.model3d.add_to_history (name+"  mirror " , f1)
        
    def pick_edge(self,name,id1,id2,component='component1'):
        """
        拾取实体的指定棱边，用于后续基于棱边的编辑/变换操作
        :param name: str, 实体名称
        :param id1: int/str, 棱边起始点ID
        :param id2: int/str, 棱边终止点ID
        :param component: str, 实体归属组件名称，默认component1
        """
        f1=f"""Pick.PickEdgeFromId "{component}:{name}", "{id1}", "{id2}"
        """
        self.cst_file.model3d.add_to_history ("Pick edge: "+str(name)+f'{id1}_{id2}' , f1)
        
    def pick_endpoint(self,name,id,component='component1'):
        """
        拾取实体的指定端点，用于后续基于端点的编辑/定位操作
        :param name: str, 实体名称
        :param id: int/str, 端点ID
        :param component: str, 实体归属组件名称，默认component1
        """
        f1=f"""Pick.PickEndpointFromId "{component}:{name}", "{id}"
        """
        self.cst_file.model3d.add_to_history ("Pick endpoint: "+str(name) , f1)
        
    def pick_face(self,name,id,component='component1'):
        """
        拾取实体的指定表面，用于后续基于表面的拉伸/旋转/端口创建操作
        :param name: str, 实体名称
        :param id: int/str, 表面ID
        :param component: str, 实体归属组件名称，默认component1
        """
        f1=f"""Pick.PickFaceFromId "{component}:{name}", "{id}"
        """
        self.cst_file.model3d.add_to_history ("Pick face: "+str(name) , f1)
        
    def set_edge(self,x1,y1,z1,x2,y2,z2):
        """
        手动创建指定两点之间的棱边，用于辅助建模/定位
        :param x1,y1,z1: float/str, 棱边起始点坐标
        :param x2,y2,z2: float/str, 棱边终止点坐标
        """
        f1=f"""Pick.AddEdge "{x1}", "{y1}", "{z1}", "{x2}", "{y2}", "{z2}"
        """
        self.cst_file.model3d.add_to_history ("Set edge " , f1)
        
    def rotation_face(self,name,angle,component='component1',material='Vacuum'):
        """
        对拾取的实体表面执行旋转拉伸，生成旋转曲面特征
        :param name: str, 目标实体名称
        :param angle: float/str, 旋转角度
        :param component: str, 实体归属组件名称，默认component1
        """
        f1=f"""With Rotate 
        .Reset 
        .Name "{name}" 
        .Component "{component}" 
        .NumberOfPickedFaces "1" 
        .Material "{material}" 
        .Mode "Picks" 
        .Angle "{angle}" 
        .Height "0.0" 
        .RadiusRatio "1.0" 
        .TaperAngle "0.0" 
        .NSteps "0" 
        .SplitClosedEdges "True" 
        .SegmentedProfile "False" 
        .DeleteBaseFaceSolid "False" 
        .ClearPickedFace "True" 
        .SimplifySolid "True" 
        .UseAdvancedSegmentedRotation "True" 
        .CutEndOff "False" 
        .Create 
        End With
        """
        self.cst_file.model3d.add_to_history ("Rotation Face: "+name , f1)

    def extrude_face(self,name,height,material='PEC',component='component1'):
        """
        对拾取的实体表面执行拉伸操作，生成凸起/凹陷特征
        :param name: str, 目标实体名称
        :param height: float/str, 拉伸高度 正数凸起 负数凹陷
        :param material: str, 拉伸后特征的材料名称，默认理想导体PEC
        :param component: str, 实体归属组件名称，默认component1
        """
        f1=f"""With Extrude 
     .Reset 
     .Name "{name}" 
     .Component "{component}" 
     .Material "{material}" 
     .Mode "Picks" 
     .Height "{height}" 
     .Twist "0.0" 
     .Taper "0.0" 
     .UsePicksForHeight "False" 
     .DeleteBaseFaceSolid "False" 
     .Keepmaterial "False" 
     .ClearPickedFace "True" 
     .Create 
End With"""
        self.cst_file.model3d.add_to_history ("Extrude Face: "+name , f1)
        
    def trace_curve(self,name,height,weight,material='PEC',curve='curve1',component='component1'):
        """
        沿指定曲线绘制带状实体（走线/传输线），用于创建微带线/共面波导等
        :param name: str, 带状实体名称
        :param height: float/str, 带状实体的厚度
        :param weight: float/str, 带状实体的宽度
        :param material: str, 带状实体材料名称，默认理想导体PEC
        :param curve: str, 走线的中心曲线名称，默认curve1
        :param component: str, 归属组件名称，默认component1
        """
        f1=f"""With TraceFromCurve 
     .Reset 
     .Name "{name}" 
     .Component "{component}" 
     .Material "{material}" 
     .Curve "{curve}:{name}" 
     .Thickness "{height}" 
     .Width "{weight}" 
     .RoundStart "False" 
     .RoundEnd "False" 
     .DeleteCurve "True" 
     .GapType "2" 
     .Create 
End With"""
        self.cst_file.model3d.add_to_history ("Trace on curve: "+str(name) , f1)

    def add_port(self,id,orientation='positive',shield=''):
        """
        创建标准波导端口/波端口，用于激励和采集S参数
        :param id: int/str, 端口编号（唯一标识）
        :param orientation: str, 端口激励方向 positive-正向 negative-反向，默认positive
        :param shield: str, 端口屏蔽类型 electric-电屏蔽 magnetic-磁屏蔽，默认electric
        """
        if shield=='electric':
            f2='.Shield "PEC"'
        elif shield=='magnetic':
            f2='.Shield "PMC"'
        else:
            f2=''
        f1=f"""With Port 
            .Reset 
            .PortNumber "{id}" 
            .Label ""
            .Folder ""
            .NumberOfModes "1"
            .AdjustPolarization "False"
            .PolarizationAngle "0.0"
            .ReferencePlaneDistance "0"
            .TextSize "50"
            .TextMaxLimit "0"
            .Coordinates "Picks"
            .Orientation "{orientation}"
            .PortOnBound "True"
            .ClipPickedPortToBound "False"
            .Xrange "-3.4", "-3.4"
            .Yrange "-0.28279441979114", "0.49280558020886"
            .Zrange "-0.4406", "0.6906"
            .XrangeAdd "0.0", "0.0"
            .YrangeAdd "0.0", "0.0"
            .ZrangeAdd "0.0", "0.0"
            .SingleEnded "False"
            .WaveguideMonitor "False"
            {f2}
            .Create 
        End With
        """
        self.cst_file.model3d.add_to_history ("Define Port: "+str(id) , f1)
        
    def discrete_port(self,r0,id,fold='',invertdrection=False):
        """
        创建离散端口（集总端口），用于射频器件的端接激励，适合芯片/封装仿真
        :param r0: float/str, 端口特征阻抗（如50欧姆）
        :param id: int/str, 端口编号（唯一标识）
        :param fold: str, 端口归属文件夹，默认空
        :param invertdrection: bool, 是否反转端口激励方向，默认False
        """
        f1=f"""With DiscreteFacePort 
     .Reset 
     .PortNumber "{id}" 
     .Type "SParameter"
     .Label ""
     .Folder "{fold}"
     .Impedance "{r0}"
     .VoltageAmplitude "1.0"
     .CurrentAmplitude "1.0"
     .Monitor "True"
     .CenterEdge "True"
     .SetP1 "True", "-10.545165835717", "9.3478692098627", "0.1"
     .SetP2 "True", "-10.545165835717", "9.3478692098627", "0"
     .LocalCoordinates "False"
     .InvertDirection "{invertdrection}"
     .UseProjection "False"
     .ReverseProjection "False"
     .FaceType "Linear"
     .Create 
End With"""
        self.cst_file.model3d.add_to_history ("Define Discrete Port: "+str(id) , f1)
        
    def lumped_element(self,id,r):
        """
        在指定位置添加集总RLC元件（串并联电阻/电感/电容），用于等效负载/匹配电路
        :param id: int/str, 元件编号
        :param r: float/str, 元件电阻值（电感电容默认0）
        """
        f1=f"""With LumpedFaceElement
     .Reset 
     .SetName "element{id}" 
     .Folder "Folder1" 
     .SetType "RLCSerial"
     .SetR "{r}"
     .SetL "0"
     .SetC "0"
     .SetGs "0"
     .SetI0 "1e-14"
     .SetT "300"
     .SetMonitor "True"
     .CircuitFileName ""
     .CircuitId "1"
     .UseCopyOnly "True"
     .UseRelativePath "False"
     .SetP1 "True", "8.1960248914249", "-18.181977909775", "0.1" 
     .SetP2 "True", "8.1960248914249", "-18.181977909775", "0" 
     .SetInvert "False" 
     .UseProjection "False" 
     .ReverseProjection "False" 
     .Create
End With
"""
        self.cst_file.model3d.add_to_history (f"Define lumped_element: {id})",f1)
        
    def define_monitor(self,name,freq):
        """
        创建场监视器，用于采集指定频率点的电磁场分布/远场辐射特性
        :param name: str, 监视器类型 可选：E-电场监视器 H-磁场监视器 Farfield-远场监视器
        :param freq: list, 需要采集场分布的频率点集合 [f1,f2,f3...]
        """
        if name=='E':
            for i in freq:
                f1=f"""With Monitor 
        .Reset 
        .Name "e-field (f={i})" 
        .Domain "Frequency" 
        .FieldType "Efield" 
        .MonitorValue "{i}" 
        .UseSubvolume "False" 
        .Coordinates "Structure" 
        .SetSubvolume "0", "0", "0", "0", "0", "0" 
        .SetSubvolumeOffset "0.0", "0.0", "0.0", "0.0", "0.0", "0.0" 
        .SetSubvolumeInflateWithOffset "False" 
        .Create 
    End With"""
                self.cst_file.model3d.add_to_history (f"Define {name} Monitor (f={i}) ",f1)
        elif name=='H':
            for i in freq:
                f1=f"""With Monitor 
        .Reset 
        .Name "h-field (f={i})" 
        .Domain "Frequency" 
        .FieldType "Hfield" 
        .MonitorValue "{i}" 
        .UseSubvolume "False" 
        .Coordinates "Structure" 
        .SetSubvolume "0", "0", "0", "0", "0", "0" 
        .SetSubvolumeOffset "0.0", "0.0", "0.0", "0.0", "0.0", "0.0" 
        .SetSubvolumeInflateWithOffset "False" 
        .Create 
    End With"""
                self.cst_file.model3d.add_to_history (f"Define {name} Monitor (f={i}) ",f1)
        elif name=='Farfield':
            for i in freq:
                f1=f"""With Monitor 
        .Reset 
        .Name "farfield (f={i})" 
        .Domain "Frequency" 
        .FieldType "Farfield" 
        .MonitorValue "{i}" 
        .UseSubvolume "False" 
        .Coordinates "Structure" 
        .SetSubvolume "0", "0", "0", "0", "0", "0" 
        .SetSubvolumeOffset "10", "10", "10", "10", "10", "10" 
        .SetSubvolumeInflateWithOffset "False" 
        .SetSubvolumeOffsetType "FractionOfWavelength" 
        .EnableNearfieldCalculation "True" 
        .Create 
    End With"""
                self.cst_file.model3d.add_to_history (f"Define {name} Monitor (f={i}) ",f1)
                
    def boundary(self,xmax='expand open',xmin='expanded open',ymax='expanded open',ymin='expanded open',zmax='expanded open',zmin='expanded open',Xsymmetry='none',Ysymmetry='none',Zsymmetry='none',ApplyInAllDirections=False,OpenAddSpaceFactor=0.5):
        """
        配置仿真区域的边界条件，决定电磁场在边界的反射/透射特性，核心仿真配置
        :param xmax/xmin: str, X轴最大/最小值边界类型 expand open-开放边界 electric-电边界 magnetic-磁边界
        :param ymax/ymin: str, Y轴最大/最小值边界类型，同X轴
        :param zmax/zmin: str, Z轴最大/最小值边界类型，同X轴
        :param Xsymmetry: str, X轴对称特性 magnetic-磁对称 electric-电对称 none-无对称，默认无对称
        :param Ysymmetry: str, Y轴对称特性，同X轴
        :param Zsymmetry: str, Z轴对称特性，同X轴
        :param ApplyInAllDirections: bool, 是否全局应用边界条件，默认True
        :param OpenAddSpaceFactor: float, 开放边界的扩展空间系数，默认0.5
        """
        f1=f"""
            With Boundary
        .Xmin "{xmax}"
        .Xmax "{xmin}"
        .Ymin "{ymax}"
        .Ymax "{ymin}"
        .Zmin "{zmax}"
        .Zmax "{zmin}"
        .Xsymmetry "{Xsymmetry}"
        .Ysymmetry "{Ysymmetry}"
        .Zsymmetry "{Zsymmetry}"
        .ApplyInAllDirections "{ApplyInAllDirections}"
        .OpenAddSpaceFactor "{OpenAddSpaceFactor}"
    End With
    """
        self.cst_file.model3d.add_to_history ('Define boundary' , f1)
        
    def exclude_simulation(self,name,component='component1'):
        """
        将指定实体排除出仿真计算，保留建模结构但不参与电磁场求解，提升仿真速度
        :param name: str, 需要排除的实体名称
        :param component: str, 实体归属组件名称，默认component1
        """
        f1=f"""Group.AddItem "solid${component}:{name}", "Excluded from Simulation"""
        self.cst_file.model3d.add_to_history ('Excluded from Simulation '+name , f1)

    def field_export(self,tree_item,save_path,mode='FixedWidth',step=-1):
        """
        field_export 的 Docstring
        
        :param self: 说明
        :param tree_item: 说明
        :param save_path: 说明
        The field data export functionality is available for the following result items:
            1D signals
            1D and 2D/3D farfields
            2D/3D field results
        """
        ascii_export = self.cst_file.model3d.ASCIIExport
        self.cst_file.model3d.SelectTreeItem("2D/3D Results\\"+tree_item)

        ascii_export.Reset()
        #Sets the absolute name of the exported file.
        ascii_export.FileName(save_path)
        # "FixedNumber":Fixed number of samples,"FixedWidth":Fixed step width
        #Number of steps or step width in all directions. 
        # Use the .Mode method to select the step definition. This setting is only available for 2D/3D field results.
        #Number of steps or step width in all directions. StepX, StepY, and StepZ are used for 2D/3D field results.
        if mode=='FixedWidth':
            ascii_export.Mode(mode)
            ascii_export.Step(step)
        elif mode=='FixedNumber':
            ascii_export.Mode(mode)
            ascii_export.Step(step)

        ascii_export.Execute()

    def patten_export(self,tree_item,save_path,
                      plottype='3d',
                      plotmode='realized gain',
                      step=-1):
        """
        field_export 的 Docstring
        
        :param self: 说明
        :param tree_item: 说明
        :param save_path: 说明
        help 文件里面 post processing->farfieldplot中里面找

        plottype:polar,cartesian,2d,2dortho,3d
        plotmode:realized gain,directivity,efield,hfield,power density
        """
        ascii_export = self.cst_file.model3d.ASCIIExport
        self.cst_file.model3d.SelectTreeItem("Farfields\\"+tree_item)
        ascii_export.FileName(save_path)
        FarfieldPlot = self.cst_file.model3d.FarfieldPlot
        #polar,cartesian,2d,2dortho,3d
        FarfieldPlot.Reset()
        FarfieldPlot.Plottype(plottype)
        FarfieldPlot.SetPlotMode(plotmode)
        FarfieldPlot.Plot()

        ascii_export.Execute()


    def export_data(self,tree_item,save_path):
        """
        export_data 的 Docstring
        
        :param self: 说明
        :param tree_item: 说明
        :param save_path: 说明
        The ASCII data export functionality is available for the following result items:
            1D signals
            1D and 2D/3D farfields
            2D/3D field results
        """
        ascii_export = self.cst_file.model3d.ASCIIExport
        self.cst_file.model3d.SelectTreeItem(tree_item)

        ascii_export.Reset()
        #Sets the absolute name of the exported file.
        ascii_export.FileName(save_path)
        # "FixedNumber":Fixed number of samples,"FixedWidth":Fixed step width
        # ascii_export.Mode("FixedWidth")
        #Number of steps or step width in all directions. 
        # Use the .Mode method to select the step definition. This setting is only available for 2D/3D field results.
        # ascii_export.Step(1)
        ascii_export.Execute()

    def sat_import(self,filename):
        f1=f"""
            With SAT
            .Reset 
            .FileName "{filename}" 
            .Id "1" 
            .Version "9.0" 
            .ScaleToUnit "0" 
            .ImportToActiveCoordinateSystem "True" 
            .Curves "True" 
            .TypePECForNewmaterial "False" 
            .Read 
        End With
        """
        self.cst_file.model3d.add_to_history ('Import Sat: '+filename , f1)
    #更改名字
    def rename(self,old,new,type='Solid'):
        """
        type: Solid or Component
        """
        f1=f"""
        {type}.Rename "{old}", "{new}"
        """
        self.cst_file.model3d.add_to_history ('Rename: '+old+' to '+new , f1) 
        
    def change_component(self,model,component):
        f1=f"""
        Solid.ChangeComponent "{model}", "{component}"
        """    
        self.cst_file.model3d.add_to_history ('Change_ChangeComponent:'+model+' to '+component , f1)
    
    def change_material(self,model,material):
        f1=f"""
        Solid.ChangeMaterial "{model}", "{material}"
        """    
        self.cst_file.model3d.add_to_history ('Change_material:'+model+' to '+material , f1)

class result():
    def __init__(self,cst_file):
        self.app_result = cst.results.ProjectFile(cst_file,allow_interactive=True)
        #获取3d结果模型对象
        self.result_module=self.app_result.get_3d()
        
    #这一块是module的接口，后续可以根据需要增加一些功能函数，比如直接获取某个tree item的结果数据等
    def get_tree_items(self):
        """
        List navigation tree items.
        """
        self.result_module.get_tree_items()
        
    def get_all_run_ids(self, max_mesh_passes_only: bool = True):
        """
        Get all existing run ids (independent of a tree path).
        In case of a mesh adaptation, max_mesh_passes_only=True yields only results with the highest mesh pass
        number, while max_mesh_passes_only=False also includes results from previous mesh passes.
        """
        return self.result_module.get_all_run_ids(max_mesh_passes_only)
    
    def get_result_item(self, treepath: str, run_id = 0, load_impedances: bool = True):
        """
        -> cst.results.ResultItem:
        Get result of a navigation tree item. 
        The setting ‘load_impedances=False’ omits automatic loading of reference impedances.
        """
        return self.result_module.get_result_item(treepath, run_id, load_impedances)
    
    def get_run_ids(self, treepath: str, skip_nonparametric: bool = False):
        """
        Get all existing run ids for a tree item. 
        The setting ‘skip_nonparametric=True’ enforces run id = 0 to be excluded from the list.
        """
        return self.result_module.get_run_ids(treepath, skip_nonparametric)
    
    #这一块是item的接口，后续可以根据需要增加一些功能函数，比如直接获取某个tree item的结果数据等
    def read_1D(self,tree_path, run_id: int = 0):
        #result_module里面
        data = self.result_module.get_result_item("1D Results\\" + tree_path, run_id)
        ss = np.asarray([data.get_xdata(), data.get_ydata()]).T
        return ss




"""
ba_filename="MZI_data\AB-light.cst"
ba_result=result(ba_filename)
print(ba_result.get_all_run_ids())

x=ba_result.result_module.get_run_ids("1D Results\\S-Parameters\\S2,1")
print(x)
ba_result.result_module.get_tree_items()

data = ba_result.result_module.get_result_item("1D Results\\S-Parameters\\S2,1")
# ba_s21=ba_result.read_1D("S-Parameters\\S2,1", run_id=3)
"""