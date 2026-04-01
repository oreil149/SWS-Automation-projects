# -*- coding: utf-8 -*- 

import arcpy  
import os     
import math
import pandas as pd


class Toolbox(object):
    def __init__(self):
        self.label = "Calculate Surface Volume of AddStorage Toolbox"
        self.alias = "CalculateSurface"  
        self.tools = [CalculateSurface]

class CalculateSurface(object):
    def __init__(self):
        self.label = "Calculate Surface Volume of AddStorage Toolbox"
        self.description = "Performs Extract Mask and Surface Volume Calculations for each Subcatchment Marked AddStorage = 1"
        self.canRunInBackground = False

    def getParameterInfo(self):
        params = []
        param0 = arcpy.Parameter(
            displayName="Subcatchments Feature Layer",  
            name="subcatchments_fc",
            datatype="DEFeatureClass",  
            parameterType="Required",
            direction="Input")  
        param1 = arcpy.Parameter(
            displayName="Output Geodatabase",
            name="output_gdb",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input")
        param2 = arcpy.Parameter(
            displayName="Model Name",
            name="model_name",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        param3 = arcpy.Parameter(
            displayName="DEM Path",
            name="dem_path",
            datatype="DERasterDataset", ## File System Raster? or "GPRasterLayer"?
            parameterType="Required",
            direction="Input")
        param4 = arcpy.Parameter(
            displayName="Output Folder",
            name="folder_path",
            datatype="DEFolder", 
            parameterType="Required",
            direction="Input")
        params.extend([param0, param1, param2, param3, param4])
        return params

    def extract_by_runoff_node(self, subcatchments_fc, output_gdb, model_name, dem_path, folder_path, messages):
        if not arcpy.Exists(subcatchments_fc):
            raise arcpy.ExecuteError(f"Subcatchments feature class not found: {subcatchments_fc}")
        if not arcpy.Exists(dem_path):
            raise arcpy.ExecuteError(f"DEM raster not found: {dem_path}")

        sel_lyr = "subcatchments_add_storage"
        arcpy.management.MakeFeatureLayer(subcatchments_fc, sel_lyr, "AddStorage = 1")
        nodes = set()
        with arcpy.da.SearchCursor(sel_lyr, ["RUNOFF_NOD"]) as cur:
            for row in cur:
                val = row[0]
                if val is not None:
                    nodes.add(val)        
        arcpy.AddMessage(f"{len(nodes)} distinct RUNOFF_NOD values")
        arcpy.SelectLayerByAttribute_management(sel_lyr, "CLEAR_SELECTION")

        for unique_node in nodes:  
            elev_list = []  
            node_str = str(unique_node).replace("'", "''")  
            where_clause = f"RUNOFF_NOD = '{node_str}'"
            group_lyr = f"group_{node_str}"
            arcpy.management.MakeFeatureLayer(sel_lyr, group_lyr, where_clause)

            out_name = f"Extract_{model_name}_{node_str}"  
            out_path = os.path.join(output_gdb, out_name)  
            outExtractByMask = arcpy.sa.ExtractByMask(dem_path, group_lyr)
            outExtractByMask.save(out_path)

            aprx = arcpy.mp.ArcGISProject("CURRENT")  
            m = aprx.activeMap
            m.addDataFromPath(out_path)
            arcpy.management.Delete(group_lyr)
            arcpy.SelectLayerByAttribute_management(sel_lyr, "CLEAR_SELECTION")

            min_elev = float(arcpy.management.GetRasterProperties(out_path, "MINIMUM").getOutput(0))  
            max_elev = float(arcpy.management.GetRasterProperties(out_path, "MAXIMUM").getOutput(0))  
            min_elev_round = round(min_elev, 2)  
            elev_list.append(min_elev_round)  

            max_elev_round = round(max_elev, 2)  
            min_whole = float(round(min_elev + 0.5))  

            text_name = f"surface_volume_{model_name}_{node_str}"  
            out_text_path = os.path.join(folder_path, text_name)  
            plane_height = min_whole

            while plane_height < max_elev_round:
                elev_list.append(plane_height)
                plane_height += 1

            elev_list.append(max_elev_round)

            for elev in elev_list:
                arcpy.ddd.SurfaceVolume(out_path, out_text_path, "BELOW", elev, z_factor=1)
                messages.addMessage(f'{elev} surface volume')  
            messages.addMessage(f'{node_str} surface volume at {out_text_path}')
            self.text_to_excel(text_name, node_str, model_name, folder_path, messages)
        return text_name

    def text_to_excel(self, text_name, node_str, model_name, folder_path, messages):
        excel_name = f"{model_name}_Excel.xlsx"  
        excel_path = os.path.join(folder_path, excel_name)
        sheet_name = f"{model_name}_{node_str}"
        text_path = os.path.join(folder_path, text_name)
        cols = ["Dataset", "Plane_Height", "Reference", "Z_Factor", "Area_2D", "Area_3D", "Volume"]
        df = pd.read_csv(text_path, sep=",", header=0, names=cols)
        df.columns = df.columns.str.strip(",")
        out_df = df[["Plane_Height", "Area_2D"]]
        messages.addMessage(out_df)
        mode = "a" if os.path.exists(excel_path) else "w"
        with pd.ExcelWriter(excel_path, engine="openpyxl", mode=mode) as writer:
            out_df.to_excel(writer, sheet_name, index=False)

        messages.addMessage(f"Wrote {len(out_df)} rows to sheet '{sheet_name}' in {excel_path}")
        return excel_path

    def execute(self, parameters, messages):
        subcatchments_fc = parameters[0].valueAsText
        output_gdb       = parameters[1].valueAsText
        model_name       = parameters[2].valueAsText
        dem_path         = parameters[3].valueAsText
        folder_path      = parameters[4].valueAsText
        arcpy.env.workspace        = output_gdb
        arcpy.env.overwriteOutput  = True
        self.extract_by_runoff_node(subcatchments_fc, output_gdb, model_name, dem_path, folder_path, messages)
