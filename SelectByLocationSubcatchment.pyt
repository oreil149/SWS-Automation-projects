# -*- coding: utf-8 -*-
import arcpy
import re
import os

class Toolbox(object):
    def __init__(self):
        self.label = "Select By Subcatchment Toolbox"
        self.alias = "SelectBySubcatchment"
        self.tools = [SelectBySubcatchment]

class SelectBySubcatchment(object):
    def __init__(self):
        self.label = "Select Features by Subcatchment Name"
        self.description = "Performs Select By Location for each unique subcatchment name."
        self.canRunInBackground = False

    def fix_name(self, name):
        name = re.sub(r'\W+', '_', name)  # Replace non-alphanumeric characters
        if name[0].isdigit():
            name = f"n_{name}"
        return name

    def getParameterInfo(self):
        params = []
        param0 = arcpy.Parameter(
            displayName="Subcatchments Feature Layer",
            name="subcatchments_fc",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input")
        param1 = arcpy.Parameter(
            displayName="Storm Catch Basins Feature Layer",
            name="storm_cb_fc",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input")
        param2 = arcpy.Parameter(
            displayName="Storm Manholes Feature Layer",
            name="storm_manhole_fc",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input")
        param3 = arcpy.Parameter(
            displayName="Output Geodatabase",
            name="output_gdb",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input")
        params.extend([param0, param1, param2, param3])
        return params

    def execute(self, parameters, messages):
        subcatchments = parameters[0].valueAsText
        storm_cb = parameters[1].valueAsText
        storm_manhole = parameters[2].valueAsText
        output_gdb = parameters[3].valueAsText
        arcpy.env.workspace = output_gdb
        arcpy.env.overwriteOutput = True
        fields = [f.name for f in arcpy.ListFields(subcatchments)]
        cb_clip_path = os.path.join(output_gdb, "STORM_CB_Clip")
        mh_clip_path = os.path.join(output_gdb, "STORM_MANHOLE_Clip")
        arcpy.gapro.ClipLayer(storm_cb, subcatchments, cb_clip_path)
        arcpy.gapro.ClipLayer(storm_manhole, subcatchments, mh_clip_path)        
        if "CB_Count" not in fields:
            arcpy.AddField_management(subcatchments, "CB_Count", "LONG")
        if "MH_Count" not in fields:
            arcpy.AddField_management(subcatchments, "MH_Count", "LONG")
        messages.addMessage(f'fields added, starting with')
        arcpy.MakeFeatureLayer_management(subcatchments, "subcatchments_layer")
        names_count = {}
        with arcpy.da.SearchCursor("subcatchments_layer", ["NAME"]) as cursor:
            for row in cursor:
                name = row[0]
                if name:
                    names_count[name] = {"CB_Count": 0, "MH_Count": 0}
        arcpy.MakeFeatureLayer_management(cb_clip_path, "storm_cb_layer")
        arcpy.MakeFeatureLayer_management(mh_clip_path, "storm_manhole_layer")
        for name in names_count:
            new_name = self.fix_name(name)
            where_clause = f"Name = '{name}'"
            messages.addMessage(f'working on {name}')
            arcpy.SelectLayerByAttribute_management("subcatchments_layer", "CLEAR_SELECTION")
            arcpy.SelectLayerByAttribute_management("subcatchments_layer", "NEW_SELECTION", where_clause)
            selected_count = int(arcpy.GetCount_management("subcatchments_layer")[0])
            messages.addMessage(selected_count)
            temp_layer = os.path.join(output_gdb, f"{new_name}_temp")
            arcpy.CopyFeatures_management("subcatchments_layer", temp_layer)
            arcpy.SelectLayerByLocation_management("storm_cb_layer", "INTERSECT", temp_layer, selection_type="NEW_SELECTION")
            cb_count = int(arcpy.GetCount_management("storm_cb_layer")[0])
            names_count[name]["CB_Count"] = cb_count
            messages.addMessage(f"cb count {names_count[name]['CB_Count']}")
            arcpy.SelectLayerByLocation_management("storm_manhole_layer", "INTERSECT", temp_layer, selection_type="NEW_SELECTION")
            mh_count = int(arcpy.GetCount_management("storm_manhole_layer")[0])
            names_count[name]["MH_Count"] = mh_count
            messages.addMessage(f"cb count {names_count[name]['MH_Count']}")
            with arcpy.da.UpdateCursor(subcatchments, ["NAME", "CB_Count", "MH_Count"], where_clause) as cursor:
                for row in cursor:
                    name = row[0]
                    if name in names_count:
                        row[1] = names_count[name]["CB_Count"]
                        row[2] = names_count[name]["MH_Count"]
                        cursor.updateRow(row)
                        messages.addMessage(f"Updated '{name}' with CB: {row[1]}, MH: {row[2]}")
                        arcpy.Delete_management(temp_layer)
                    else:
                        continue
        arcpy.CalculateField_management(subcatchments, "CB_Combined", "!CB_Count! + !MH_Count!", "PYTHON")

          


