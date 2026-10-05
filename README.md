# USD Material Renamer for Blender

[![Blender](https://img.shields.io/badge/Blender-4.0%20%7C%204.2%20%7C%205.x-orange.svg)](https://www.blender.org/)
[![USD](https://img.shields.io/badge/USD-Universal%20Scene%20Description-blue.svg)](https://openusd.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A production-grade Blender add-on that renames mesh objects and datablocks according to their assigned materials, specifically tailored for **USD (Universal Scene Description)** lookdev pipelines in **Houdini Solaris** and **Gaffer**.

---

## The Problem It Solves

When exporting assets (such as vehicles, environments, or props) from Blender to USD for lookdev in Solaris or Gaffer, artists rely on wildcard pattern matching (e.g. `.../*_CarPaint`) to bind materials in batch.

However, Blender's default behaviors introduce critical pipeline issues:
1. **The `.001` Duplication Trap**: If you have 4 wheels with material `Rubber`, standard renaming results in `Wheel_Rubber`, `Wheel_Rubber.001`, `Wheel_Rubber.002`. In USD, dots become underscores (`Wheel_Rubber_001`), **breaking suffix matching (`*_Rubber`)**.
2. **Invalid USD Identifiers**: Characters like spaces, dashes, periods, or parentheses (`Wheel - Front (L)`) are illegal in USD `SdfPath` tokens and get mangled.
3. **Multi-Material Meshes**: Single meshes with multiple material slots cause unexpected material overrides unless split into discrete prims.
4. **Mismatched Shape Prims**: When `obj.data.name` does not match `obj.name`, USD exporters can create conflicting child mesh prim names.

---

## Features

- **USD Suffix Guarantee**: Numbering is placed **before** the material suffix (`Wheel_01_Rubber`, `Wheel_02_Rubber`), guaranteeing that **every single prim ends strictly with the material name**.
- **Strict USD Sanitization**: Automatically converts names to valid USD tokens (`[a-zA-Z0-9_]`) without illegal characters.
- **Auto-Split Multi-Material Meshes**: Optionally separates meshes that have faces assigned to different materials into individual 1-material meshes, while preserving transforms, hierarchy, and UVs.
- **Unify Material Duplicates**: Automatically strips Blender duplicate suffixes (`Rubber.001` $\rightarrow$ `Rubber`) so identical materials map to one unified shader.
- **Mesh Data Synchronization**: Keeps `obj.data.name` in sync with `obj.name`, preventing USD Shape prim discrepancies.
- **USD Primvar Injection**: Automatically embeds an `obj["usd_material"]` custom property on each object for collection and primvar querying in Solaris/Gaffer.
- **Idempotent**: Re-running the tool will never stack suffixes (`Hood_CarPaint_CarPaint`).

---

## Installation

### Method 1: Single File Add-on (All Blender Versions)
1. Download [`usd_material_renamer.py`](usd_material_renamer.py).
2. In Blender, go to **Edit** $\rightarrow$ **Preferences** $\rightarrow$ **Add-ons**.
3. Click the top-right dropdown arrow $\rightarrow$ **Install from Disk...** (or click **Install...** in Blender 4.0/4.1).
4. Select `usd_material_renamer.py` and enable the checkbox for **USD Material Renamer**.

### Method 2: Manual Installation
Copy `usd_material_renamer.py` into your Blender add-ons directory:
* **Linux**: `~/.config/blender/<version>/scripts/addons/`
* **Windows**: `%APPDATA%\Blender Foundation\Blender\<version>\scripts\addons\`
* **macOS**: `~/Library/Application Support/Blender/<version>/scripts/addons/`

---

## How to Use

1. Open the 3D Viewport in Blender.
2. Press **`N`** to open the Sidebar panel.
3. Switch to the **USD Tools** tab.
4. Adjust settings as needed:
   - **Only Selected**: Process only selected objects, or the entire scene.
   - **Split Multi-Material Meshes**: Automatically split meshes with multiple materials into separate single-material objects.
   - **Strip Material Numbers**: Treat `Rubber.001` as `Rubber`.
   - **Sync Mesh Data Name**: Keep datablock names in sync with object names.
   - **Set 'usd_material' Property**: Injects custom property for USD primvars.
5. Click **Rename Meshes for USD**.

---

## Downstream Pipeline Guide

### 1. Exporting USD from Blender
Go to **File** $\rightarrow$ **Export** $\rightarrow$ **Universal Scene Description (`.usd`, `.usdc`, `.usda`)**:
* Enable **Normals** and **UV Coordinates**.
* (Optional) Enable **Custom Properties** to export the `usd_material` primvar.

### 2. Houdini Solaris (USD)
In Solaris, create an **Assign Material** LOP:
* Set **Primitives** pattern to:
  ```text
  .../*_RX500_Body_Paint
  ```
  *(or `*_*_Rubber` to match all numbered wheels: `Wheel_01_Rubber`, `Wheel_02_Rubber`)*
* Set **Material Path** to your shader:
  ```text
  /materials/M_CarPaint
  ```
* Prims ending with `*_noMat` will immediately highlight any unassigned geometry.

### 3. Gaffer
In Gaffer, add a **MaterialAssignment** node:
* Set the target **PathFilter** to:
  ```text
  .../*_RX500_Body_Paint
  ```
* Connect your renderer's shader into the material plug.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
