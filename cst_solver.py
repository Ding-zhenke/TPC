# -*- coding: utf-8 -*-
"""
Created on Mon Oct 20 11:37:16 2025

@author: PC
"""

import sys
import os
# ensure the CST python libraries path is added correctly (use raw string)
sys.path.append(r"D:\CST2025\location\AMD64\python_cst_libraries")
import cst
import cst.interface
import cst.results

print(cst.__file__) 

class setup():
    def __init__(self,filename):
        #运行交互式
        self.t=0
        self.project = cst.interface.DesignEnvironment()
        # Normalize filename to absolute path and check existence before opening
        try:
            filename_abs = os.path.abspath(filename)
        except Exception:
            filename_abs = filename

        if not os.path.exists(filename_abs):
            # Provide a clearer error when the file cannot be found
            raise FileNotFoundError(f"CST project file not found: {filename_abs}")

        try:
            # Attempt to open the CST project and activate it. If this fails,
            # capture the underlying exception and raise a clearer RuntimeError
            self.cst_file = self.project.open_project(filename_abs)
            self.cst_file.activate()
        except Exception as e:
            # Repackage the error with helpful debugging information
            raise RuntimeError(
                f"Failed to open the CST project '{filename_abs}'. "
                f"Underlying error: {e!s}.\n"
                f"Possible causes: file is not a valid .cst project, CST automation not available, or permissions/encoding issues."
            )
    def T_solver(self):
        pass
        
    def freq_limit(self,fmin,fmax):
        f1 = """
        'Set Freq
        Solver.FrequencyRange %s, %s
        """%(fmin,fmax)
        # print(f1)
        self.cst_file.model3d.add_to_history ("Freq_range" , f1)
    def new_material(self,name):
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
        self.cst_file.model3d.run_solver()
    def close(self):
        self.cst_file.close()
        self.project.close()
    def para(self,name,value,log_flag=0):
        #创建参数
        self.cst_file.model3d.StoreParameter(f"{name}",value)
        # 加载到项目历史，使得参数生效
        if log_flag==1:
            self.cst_file.model3d.full_history_rebuild()    
    def expression(self,name,value):
        #创建参数
        self.cst_file.model3d.RestoreParameterExpression(f"{name}",f"{value}")         
    def new_componet(self,name):
        f1="""
        '  new component: %s
        Component.New "%s" 
        """%(name,name)
        self.cst_file.model3d.add_to_history ("Freq_range " , f1)
    def square(self,xmin,xmax,
                    ymin,ymax,
                    zmin,zmax,
                    name,
                    component='component1',
                    Material='PEC'):
        f1 = f"""
        With Brick
            .Reset 
            .Name "{name}"
            .Component "{component}"
            .Material "{Material}" 
            .Xrange "{xmin}", "{xmax}" 
            .Yrange "{ymin}", "{ymax}"
            .Zrange "{zmin}", "{zmax}"
            .Create
        End With
        """
        # print(f1)
        self.cst_file.model3d.add_to_history ("Square: "+name , f1)
    def cylinder(self,center,r,h,name,axis='z',component='component1',
                    Material='PEC'):
        if axis=='z':
            f1=f"""
            With Cylinder 
            .Reset 
            .Name "{name}" 
            .Component "{component}" 
            .Material "{Material}" 
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
    def triangle(self,a,h,center,theta,name,curve,materials='Silicon (lossy)'):
        data=[
                [f"0",f"{a}/sqr(3)"],
                [f"-{a}/(2)",f"-{a}/2/sqr(3)"],
                [f"{a}/(2)",f"-{a}/2/sqr(3)"],
                ["0",f"{a}/sqr(3)"]
                ]
        f1=self.polyline(data,name,curve,log_flag=0)
        f2=self.extrude(f'{curve}:{name}',f'{name}',f'{h}',component='component1',materials=materials,log_flag=0)
        f1=f1+f2
        if theta!=[0,0,0]:
            f3=self.rotation(f'{name}',theta,component='component1',log_flag=0)
            f1=f1+f3
        f4=self.translate(f'{name}',center,component='component1',log_flag=0)
        f1=f1+f4
        self.cst_file.model3d.add_to_history (" Triangle: "+name , f1)
    def hexagon(self,a,h,center,theta,name,curve='curve1',component='component1',materials='Silicon (lossy)'):
        data=[]
        for i in range(7):
            tmp=[f'({a})*cosd({i*60})',f'({a})*sind({i*60})']
            data.append(tmp)
        f1=self.polyline(data,name,log_flag=0)
        f2=self.extrude(f'{curve}:{name}',f'{name}',f'{h}',component=component,materials=materials,log_flag=0)
        f1=f1+f2
        if theta!=[0,0,0]:
            f3=self.rotation(f'{name}',theta,component=component,log_flag=0)
            f1=f1+f3
        f4=self.translate(f'{name}',center,component=component,log_flag=0)
        f1=f1+f4
        self.cst_file.model3d.add_to_history (" Hexagon: "+name , f1)
    def polyline(self,data,name='1',curve='curve1',log_flag=1):
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
        # print(f1)
        if log_flag==1:
            self.cst_file.model3d.add_to_history (" Polyline "+name , f1)
        return f1
    def arc(self,center,p,angle,name="arc1",curve='curve1',orientation='Counterclockwise',log_flag=1):
        #orientation='Clockwise' OR 'Counterclockwise'
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
    def extrude(self, curve, name, thickness, component='component1', materials='PEC',log_flag=1):
        #.Curve "curve1:polygon2"
        f1=f"""
        With ExtrudeCurve
             .Reset 
             .Name "{name} "
             .Component "{component}"
             .Material "{materials}"
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
    def rotation(self,name,angle,center=['0','0','0'],repetition=1,component='component1',copy=False,unite=False,
                 log_flag=1):
        
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
        # if repetitions<1:
        #     repetitions=1
        #     print("Repetitions不能小于1，已自动设置为1")
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
    def add(self,name1,name2,component='component1'):
        f1=f"""
        Solid.Add "{component}:{name1}", "{component}:{name2}"
        """
        self.cst_file.model3d.add_to_history (name1+" add "+name2 , f1)
    def substract(self,name1,name2,component='component1'):
        f1=f"""
        Solid.Subtract "{component}:{name1}", "{component}:{name2}"
        """
        self.cst_file.model3d.add_to_history (name1+" substract "+name2 , f1)
    def insert(self,name1,name2,component='component1'):
        f1=f"""
        Solid.Insert "{component}:{name1}", "{component}:{name2}"
        """
        self.cst_file.model3d.add_to_history (name1+" Insert "+name2 , f1)
    def intersect(self,name1,name2,component='component1'):
        f1=f"""
        Solid.Intersect "{component}:{name1}", "{component}:{name2}"
        """
        self.cst_file.model3d.add_to_history (name1+" intersect "+name2 , f1)
    def mirror(self,name,center,plane,component='component1',object='Shape',copy=False,unite=False):
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
        f1=f"""Pick.PickEdgeFromId "{component}:{name}", "{id1}", "{id2}"
        """
        self.cst_file.model3d.add_to_history ("Pick edge: "+str(name)+f'{id1}_{id2}' , f1)
    def pick_endpoint(self,name,id,component='component1'):
        #选择端点
        f1=f"""Pick.PickEndpointFromId "{component}:{name}", "{id}"
        """
        self.cst_file.model3d.add_to_history ("Pick endpoint: "+str(name) , f1)
    def pick_face(self,name,id,component='component1'):
        #选择面
        f1=f"""Pick.PickFaceFromId "{component}:{name}", "{id}"
        """
        self.cst_file.model3d.add_to_history ("Pick face: "+str(name) , f1)
    def set_edge(self,x1,y1,z1,x2,y2,z2):
        f1=f"""Pick.AddEdge "{x1}", "{y1}", "{z1}", "{x2}", "{y2}", "{z2}"
        """
        self.cst_file.model3d.add_to_history ("Set edge " , f1)
    def rotaion_face(self,name,angle,component='component1'):
        f1=f"""With Rotate 
        .Reset 
        .Name "{name}" 
        .Component "{component}" 
        .NumberOfPickedFaces "1" 
        .Material "Copper (annealed)" 
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
        self.cst_file.model3d.add_to_history ("Rotaion Face: "+name , f1)
    def exdude_face(self,name,height,materials='PEC',component='component1'):
        f1=f"""With Extrude 
     .Reset 
     .Name "{name}" 
     .Component "{component}" 
     .Material "{materials}" 
     .Mode "Picks" 
     .Height "{height}" 
     .Twist "0.0" 
     .Taper "0.0" 
     .UsePicksForHeight "False" 
     .DeleteBaseFaceSolid "False" 
     .KeepMaterials "False" 
     .ClearPickedFace "True" 
     .Create 
End With"""
        self.cst_file.model3d.add_to_history ("Extrude Face: "+name , f1)
    def trace_curve(self,name,height,weight,materials='PEC',curve='curve1',component='component1'):
        f1=f"""With TraceFromCurve 
     .Reset 
     .Name "{name}" 
     .Component "{component}" 
     .Material "{materials}" 
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

    def add_port(self,id,orientation='positive'):
        #positive or negative
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
            .Create 
        End With
        """
        self.cst_file.model3d.add_to_history ("Define Port: "+str(id) , f1)
    def discrete_port(self,r0,id,fold='',invertdrection=False):
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
    def define_monitor(self,name,freq,):
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
    def boundary(self,xmax='expand open',xmin='expanded open',ymax='expanded open',ymin='expanded open',zmax='expanded open',zmin='expanded open',
                 Xsymmetry='none',Ysymmetry='none',Zsymmetry='none',ApplyInAllDirections=True,OpenAddSpaceFactor=0.5):
        #设置边界条件 electric expand open 
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
        f1=f"""Group.AddItem "solid${component}:{name}", "Excluded from Simulation"""
        self.cst_file.model3d.add_to_history ('Excluded from Simulation '+name , f1)