bl_info = {
    "name": "USD Material Renamer",
    "author": "Teja Ravi Varma",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > USD Tools",
    "description": "Renames meshes according to assigned materials for USD pipelines (Solaris, Gaffer), avoiding .001 duplication traps.",
    "category": "Pipeline",
    "doc_url": "https://github.com/TEJARAVIVARMA/usd-material-renamer",
}

import bpy
import re
from collections import defaultdict
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup

# ==============================================================================
# CORE LOGIC
# ==============================================================================

def sanitize_usd_name(name: str) -> str:
    """Sanitizes a string to conform strictly to USD SdfPath / TfToken identifier rules."""
    if not name:
        return "unnamed"
    clean = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    clean = re.sub(r'_+', '_', clean).strip('_')
    if clean and clean[0].isdigit():
        clean = f"_{clean}"
    return clean or "unnamed"


def clean_material_token(mat_name: str, strip_duplicates: bool = True) -> str:
    """Sanitizes material name and optionally strips Blender duplicate numbers (.001)."""
    name = mat_name
    if strip_duplicates:
        name = re.sub(r'\.\d+$', '', name)
    return sanitize_usd_name(name)


def clean_mesh_slots(obj):
    """Removes empty slots and unused materials from the mesh datablock."""
    if not obj.data or not hasattr(obj.data, "polygons") or len(obj.material_slots) == 0:
        return
    used_indices = set(p.material_index for p in obj.data.polygons)
    for i in range(len(obj.material_slots) - 1, -1, -1):
        slot = obj.material_slots[i]
        if not slot.material or i not in used_indices:
            obj.data.materials.pop(index=i)


def get_assigned_materials(obj):
    """Returns unique materials actually assigned to polygons of the mesh."""
    if not obj.data or not hasattr(obj.data, "polygons"):
        return [s.material for s in obj.material_slots if s.material]
    
    used_indices = set(p.material_index for p in obj.data.polygons)
    mats = []
    for idx in sorted(used_indices):
        if idx < len(obj.material_slots):
            mat = obj.material_slots[idx].material
            if mat and mat not in mats:
                mats.append(mat)
    if not mats:
        mats = [s.material for s in obj.material_slots if s.material]
    return mats


def extract_base_name(name: str, known_materials: set, separator: str = "_") -> str:
    """Extracts base name, cleanly stripping old material suffixes and duplicate numbers."""
    clean = re.sub(r'\.\d+$', '', name)
    
    for mat in sorted(known_materials, key=len, reverse=True):
        suffix = f"{separator}{mat}"
        if clean.endswith(suffix):
            clean = clean[:-len(suffix)]
            break
            
    clean = re.sub(rf'{re.escape(separator)}\d+$', '', clean)
    return sanitize_usd_name(clean)


def split_multi_material_objects(objects):
    """Splits meshes with multiple materials into separate single-material objects."""
    processed = []
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
        
    for obj in objects:
        if obj.type != 'MESH':
            continue
            
        mats = get_assigned_materials(obj)
        if len(mats) > 1:
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.separate(type='MATERIAL')
            bpy.ops.object.mode_set(mode='OBJECT')
            
            new_objs = list(bpy.context.selected_objects)
            processed.extend(new_objs)
        else:
            processed.append(obj)
            
    return processed


def execute_usd_renamer(
    context,
    only_selected=False,
    split_by_material=False,
    multi_mat_policy='JOIN',
    strip_mat_duplicates=True,
    clean_unused_slots=True,
    sync_data_name=True,
    set_usd_property=True,
    separator="_",
    no_mat_suffix="noMat"
):
    if only_selected:
        targets = [o for o in context.selected_objects if o.type == 'MESH']
    else:
        targets = [o for o in context.scene.objects if o.type == 'MESH']
        
    if not targets:
        return 0, "No mesh objects found to process."

    if split_by_material:
        targets = split_multi_material_objects(targets)
        
    if clean_unused_slots:
        for obj in targets:
            clean_mesh_slots(obj)

    all_known_materials = {clean_material_token(m.name, strip_mat_duplicates) for m in bpy.data.materials if m}
    all_known_materials.add(no_mat_suffix)

    groups = defaultdict(list)
    for obj in targets:
        mats = get_assigned_materials(obj)
        if not mats:
            mat_suffix = no_mat_suffix
        elif len(mats) == 1:
            mat_suffix = clean_material_token(mats[0].name, strip_mat_duplicates)
        else:
            if multi_mat_policy == 'PRIMARY':
                mat_suffix = clean_material_token(mats[0].name, strip_mat_duplicates)
            elif multi_mat_policy == 'SKIP':
                continue
            else: # JOIN
                mat_suffix = separator.join(clean_material_token(m.name, strip_mat_duplicates) for m in mats)
                
        base_name = extract_base_name(obj.name, all_known_materials, separator)
        groups[(base_name, mat_suffix)].append(obj)

    planned_renames = []
    for (base, mat_suffix), objs in groups.items():
        if len(objs) == 1:
            target_name = f"{base}{separator}{mat_suffix}"
            planned_renames.append((objs[0], target_name, mat_suffix))
        else:
            for idx, obj in enumerate(objs, start=1):
                target_name = f"{base}{separator}{idx:02d}{separator}{mat_suffix}"
                planned_renames.append((obj, target_name, mat_suffix))

    # Pass 1: Temporary names to prevent duplicate collision auto-suffixing
    for idx, (obj, _, _) in enumerate(planned_renames):
        obj.name = f"__usd_tmp_{idx:05d}__"

    # Pass 2: Final USD names
    renamed_count = 0
    seen_mesh_data = set()
    for obj, target_name, mat_suffix in planned_renames:
        obj.name = target_name
        renamed_count += 1
        
        if sync_data_name and obj.data and obj.data not in seen_mesh_data:
            obj.data.name = target_name
            seen_mesh_data.add(obj.data)
            
        if set_usd_property:
            obj["usd_material"] = mat_suffix

    return renamed_count, f"Successfully renamed {renamed_count} mesh object(s) for USD."


# ==============================================================================
# PROPERTIES & OPERATORS
# ==============================================================================

class USDRenamerSettings(PropertyGroup):
    only_selected: BoolProperty(
        name="Only Selected",
        description="Process only currently selected mesh objects",
        default=False
    )
    split_by_material: BoolProperty(
        name="Split Multi-Material Meshes",
        description="Separate polygons assigned to different materials into individual 1-material objects",
        default=False
    )
    multi_mat_policy: EnumProperty(
        name="Multi-Material Policy",
        description="Action when an object has multiple materials and splitting is disabled",
        items=[
            ('JOIN', "Join Names", "Append all material names (e.g. Mesh_Paint_Glass)"),
            ('PRIMARY', "Primary Material", "Append only the first assigned material"),
            ('SKIP', "Skip Objects", "Leave multi-material objects untouched"),
        ],
        default='JOIN'
    )
    strip_mat_duplicates: BoolProperty(
        name="Strip Material Numbers",
        description="Strip Blender duplicate suffixes (.001, .002) from material names so shaders unify",
        default=True
    )
    clean_unused_slots: BoolProperty(
        name="Clean Unused Slots",
        description="Remove unused or empty material slots from meshes",
        default=True
    )
    sync_data_name: BoolProperty(
        name="Sync Mesh Data Name",
        description="Set obj.data.name identical to obj.name to avoid USD Shape prim naming mismatches",
        default=True
    )
    set_usd_property: BoolProperty(
        name="Set 'usd_material' Property",
        description="Add custom property 'usd_material' on the object for USD Primvar / collection queries",
        default=True
    )
    separator: StringProperty(
        name="Separator",
        description="Delimiter between name components",
        default="_",
        maxlen=4
    )
    no_mat_suffix: StringProperty(
        name="No Material Suffix",
        description="Suffix applied to meshes without any assigned material",
        default="noMat"
    )


class OBJECT_OT_usd_material_rename(Operator):
    """Rename meshes to include their assigned material name for USD pipelines"""
    bl_idname = "object.usd_material_rename"
    bl_label = "Rename Meshes for USD"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.usd_renamer_settings
        count, msg = execute_usd_renamer(
            context,
            only_selected=settings.only_selected,
            split_by_material=settings.split_by_material,
            multi_mat_policy=settings.multi_mat_policy,
            strip_mat_duplicates=settings.strip_mat_duplicates,
            clean_unused_slots=settings.clean_unused_slots,
            sync_data_name=settings.sync_data_name,
            set_usd_property=settings.set_usd_property,
            separator=settings.separator,
            no_mat_suffix=settings.no_mat_suffix
        )
        if count > 0:
            self.report({'INFO'}, msg)
        else:
            self.report({'WARNING'}, msg)
        return {'FINISHED'}


# ==============================================================================
# UI PANEL
# ==============================================================================

class VIEW3D_PT_usd_material_renamer(Panel):
    """Creates a Panel in the 3D Viewport Sidebar (N panel)"""
    bl_label = "USD Material Renamer"
    bl_idname = "VIEW3D_PT_usd_material_renamer"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'USD Tools'

    def draw(self, context):
        layout = self.layout
        settings = context.scene.usd_renamer_settings

        # Action Button
        row = layout.row(align=True)
        row.scale_y = 1.6
        row.operator("object.usd_material_rename", icon='MATERIAL', text="Rename Meshes for USD")

        layout.separator()

        # Scope Box
        box = layout.box()
        box.label(text="Scope & Geometry:", icon='FILTER')
        box.prop(settings, "only_selected")
        box.prop(settings, "split_by_material")
        if not settings.split_by_material:
            box.prop(settings, "multi_mat_policy", text="")

        # USD Pipeline Conventions Box
        box = layout.box()
        box.label(text="USD Pipeline Options:", icon='TOOL_SETTINGS')
        box.prop(settings, "strip_mat_duplicates")
        box.prop(settings, "sync_data_name")
        box.prop(settings, "set_usd_property")
        box.prop(settings, "clean_unused_slots")

        # Naming Details Box
        box = layout.box()
        box.label(text="Naming Tokens:", icon='SORTALPHA')
        box.prop(settings, "separator")
        box.prop(settings, "no_mat_suffix")

        # Scene Info Summary Box
        box = layout.box()
        box.label(text="Scene Status:", icon='INFO')
        mesh_count = len([o for o in context.scene.objects if o.type == 'MESH'])
        sel_count = len([o for o in context.selected_objects if o.type == 'MESH'])
        mat_count = len(bpy.data.materials)
        
        col = box.column(align=True)
        col.label(text=f"Total Meshes: {mesh_count} (Selected: {sel_count})")
        col.label(text=f"Total Materials: {mat_count}")


# ==============================================================================
# REGISTRATION
# ==============================================================================

classes = (
    USDRenamerSettings,
    OBJECT_OT_usd_material_rename,
    VIEW3D_PT_usd_material_renamer,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.usd_renamer_settings = bpy.props.PointerProperty(type=USDRenamerSettings)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.usd_renamer_settings


if __name__ == "__main__":
    register()
