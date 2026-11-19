bl_info = {
    "name": "Blender Fast64 AI Bridge Diagnostics",
    "author": "hesta-lang",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > AI Bridge",
    "description": "Local diagnostics for Blender and Fast64 AI Bridge",
    "category": "3D View",
}

import bpy

class BFAI_OT_diagnostics(bpy.types.Operator):
    bl_idname = "bfai.diagnostics"
    bl_label = "Check Fast64"
    def execute(self, context):
        loaded = [m for m in __import__("sys").modules if "fast64" in m.lower()]
        self.report({"INFO"}, "Fast64 modules: " + str(len(loaded)))
        return {"FINISHED"}

class BFAI_PT_panel(bpy.types.Panel):
    bl_label = "AI Bridge"
    bl_idname = "BFAI_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Bridge"
    def draw(self, context):
        self.layout.operator("bfai.diagnostics")

classes = (BFAI_OT_diagnostics, BFAI_PT_panel)
def register():
    for cls in classes: bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)
if __name__ == "__main__": register()
