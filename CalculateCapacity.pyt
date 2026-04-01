# -*- coding: utf-8 -*-
import arcpy
import os
class Toolbox(object):
    def __init__(self):
        self.label = "Calculate Capacity of Subcatchment Toolbox"
        self.alias = "CalculateCapacity"
        self.tools = [CalculateCapacity]

class CalculateCapacity(object):
    def __init__(self):
        self.label = "Calculate Capacity of Subcatchment Toolbox"
        self.description = "Performs Capacity Claculation for each subcatchment"
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
            displayName="Water Boundary Feature Layer",
            name="WaterBoundaryFeatureLayer",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input")
        param3 = arcpy.Parameter(
            displayName="Bridge Pts Feature Layer",
            name="BridgePtsFeatureLayer",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input")
        # param4 = arcpy.Parameter(
        #     displayName="Output Folder File Path",
        #     name="output_folder_filepath",
        #     datatype="DEFolder",
        #     parameterType="Required",
        #     direction="Input")
        params.extend([param0, param1, param2, param3]) #param4
        return params
    
    def calculate_flow_capacity(self, cb_combined):
        return cb_combined * 2.5
    
    def filter_water_bndry(self, subcatchments, water, output_gdb, bridges, subcatchments_name):
        arcpy.MakeFeatureLayer_management(subcatchments, "subcatchment_layer")
        water_clip_output = os.path.join(output_gdb, "Water_Clip")
        arcpy.gapro.ClipLayer(water, subcatchments, water_clip_output)
        aprx = arcpy.mp.ArcGISProject("CURRENT")
        map_obj = aprx.listMaps()[0]
        water_Clip = map_obj.addDataFromPath(water_clip_output)
        arcpy.SelectLayerByLocation_management(in_layer="subcatchment_layer",overlap_type="INTERSECT",select_features=water_Clip,selection_type="NEW_SELECTION")
        with arcpy.da.UpdateCursor("subcatchment_layer", ["Flag_Water"]) as cursor:
            for row in cursor:
                row[0] = 1
                cursor.updateRow(row)
        arcpy.SelectLayerByLocation_management(in_layer="subcatchment_layer",overlap_type="INTERSECT",select_features=bridges,selection_type="SUBSET_SELECTION")
        ## Consider adding buffer to bridges to get both directions of the bridge if missing???
        with arcpy.da.UpdateCursor("subcatchment_layer", ["Bridges_Water"]) as cursor:
            for row in cursor:
                row[0] = 1
                cursor.updateRow(row)
        arcpy.SelectLayerByLocation_management(in_layer="subcatchment_layer",overlap_type="INTERSECT",select_features=water_Clip,selection_type="NEW_SELECTION")
        output_fc = os.path.join(output_gdb, f"{subcatchments_name}_Overlapping_Water")
        arcpy.CopyFeatures_management("subcatchment_layer", output_fc)
        aprx = arcpy.mp.ArcGISProject("CURRENT")
        map_obj = aprx.listMaps()[0]
        map_obj.addDataFromPath(output_fc)
        arcpy.Delete_management("subcatchment_layer")
        
    def execute(self, parameters, messages):
        subcatchments = parameters[0].valueAsText
        output_gdb = parameters[1].valueAsText
        water = parameters[2].valueAsText
        bridges = parameters[3].valueAsText
        # output_filepath = parameters[4].valueAsText
        subcatchments_name = os.path.basename(subcatchments)
        arcpy.env.workspace = output_gdb
        arcpy.env.overwriteOutput = True
        subcatchment_data = {}
        arcpy.AddField_management(subcatchments, "FLOW_CAP", "DOUBLE")
        arcpy.AddField_management(subcatchments, "UTIL_PCT_10yr", "DOUBLE")
        arcpy.AddField_management(subcatchments, "CAP_DEFCT_10yr", "DOUBLE")
        arcpy.AddField_management(subcatchments, "IN_ADD_10yr", "DOUBLE")
        arcpy.AddField_management(subcatchments, "Flag_Water", "DOUBLE")
        arcpy.AddField_management(subcatchments, "Bridges_Water", "DOUBLE")
        arcpy.AddField_management(subcatchments, "Flag_NoCBs_Mpls", "DOUBLE")
        arcpy.CalculateField_management(subcatchments, "Flag_NoCBs_Mpls", expression="0", expression_type="PYTHON3")
        arcpy.management.AlterField(subcatchments, "PEAKRUNOFF", new_field_name="PEAKRUNOFF_10yr")
        with arcpy.da.SearchCursor(subcatchments, ["NAME", "CB_Combined", "PEAKRUNOFF_10yr"]) as cursor: ## took out "PEAKRUNOFF" for 2yr
            for row in cursor:
                name = row[0]
                if name:
                    subcatchment_data[name] = {
                        "CB_Combined": row[1],  
                        "PEAKRUNOFF_10yr": row[2]
                    }
        for name, sub_feature in subcatchment_data.items():
            messages.addMessage(f'feature id {name}')
            cb_combined = float(sub_feature["CB_Combined"])
            peak_runoff_10yr = float(sub_feature["PEAKRUNOFF_10yr"])
            flow_cap = self.calculate_flow_capacity(cb_combined)
            sub_feature["FLOW_CAP"] = flow_cap
            sub_feature["CAP_DEFCT_10yr"] = flow_cap - peak_runoff_10yr
            if peak_runoff_10yr > flow_cap:
                ''' calculation based on cfs value 2.5 '''
                in_add_10yr = ((peak_runoff_10yr - flow_cap) / 2.5) + 0.4  # The 0.4 is a rounding value
            else:
                in_add_10yr = 0
            sub_feature["IN_ADD_10yr"] = round(in_add_10yr) # assigns calculated and rounded in_add_10yr val to the sub_feature
            if flow_cap > 0:
                util_pct_10yr = (peak_runoff_10yr / flow_cap) * 100
            else:
                util_pct_10yr = 0
            sub_feature["UTIL_PCT_10yr"] = util_pct_10yr
        with arcpy.da.UpdateCursor(subcatchments, ["NAME", "FLOW_CAP", "CAP_DEFCT_10yr", "IN_ADD_10yr", "UTIL_PCT_10yr"]) as cursor: 
            for row in cursor:
                sub_name = row[0]
                sub_data = subcatchment_data.get(sub_name)
                if sub_data:
                    row[1] = sub_data["FLOW_CAP"]
                    row[2] = sub_data["CAP_DEFCT_10yr"]
                    row[3] = sub_data["IN_ADD_10yr"]
                    row[4] = sub_data["UTIL_PCT_10yr"]
                    cursor.updateRow(row)
        self.filter_water_bndry(subcatchments, water, output_gdb, bridges, subcatchments_name)
        keep_layers = [subcatchments, "STORM_CB_Clip", "STORM_MANHOLE_Clip", water, bridges, f"{subcatchments_name}_Overlapping_Water", "Water_Clip"]
        for lyr in arcpy.ListFeatureClasses():
            if lyr not in keep_layers:
                arcpy.Delete_management(lyr)
        aprx = arcpy.mp.ArcGISProject("CURRENT")
        map_obj = aprx.listMaps()[0]
        map_obj.addDataFromPath(os.path.join(output_gdb, "Water_Clip"))
        map_obj.addDataFromPath(os.path.join(output_gdb, subcatchments))
        map_obj.addDataFromPath(bridges)
        # final_table = os.path.join(output_gdb, f"Calculated_{subcatchments_name}")
        # arcpy.CopyFeatures_management(subcatchments, final_table)
        # output_filepath_table = os.path.join(output_filepath, f"Calculated_{subcatchments_name}.xlsx")
        # arcpy.conversion.TableToExcel(final_table, output_filepath_table)





