"""Editor menu / toolbar entries that open the ReconstructionBridge window.

Registered automatically at editor startup by init_unreal.py.
The window itself is the Editor Utility Widget EUW_ReconstructionBridge.
"""

import unreal

EUW_ASSET_PATH = "/ReconstructionBridge/EUW_ReconstructionBridge"

MENU_OWNER = "ReconstructionBridge"
SECTION_NAME = "ReconstructionBridge"
ENTRY_NAME = "OpenReconstructionBridge"
LABEL = "Reconstruction Bridge"
TOOLTIP = "Open the Reconstruction Bridge (ExMesh image-to-mesh) window"
ICON_STYLE = "EditorStyle"
ICON_NAME = "ClassIcon.StaticMesh"

OPEN_COMMAND = "import reconstruction_bridge_menu; reconstruction_bridge_menu.open_window()"

SETUP_ENTRY_NAME = "ReconstructionBridgeSetup"
SETUP_LABEL = "Reconstruction Bridge Setup..."
SETUP_TOOLTIP = "Install or repair ExMesh, the conda envs and COLMAP (needs Miniconda)"
SETUP_ICON_NAME = "Icons.Download"
SETUP_COMMAND = "import reconstruction_setup; reconstruction_setup.run_setup()"

# Menus extended by this module.
TOOLS_MENU = "LevelEditor.MainMenu.Tools"
TOOLBAR_MENU = "LevelEditor.LevelEditorToolBar.User"


def open_window():
    """Spawn (or focus) the ReconstructionBridge editor utility tab."""
    widget_bp = None
    if unreal.EditorAssetLibrary.does_asset_exist(EUW_ASSET_PATH):
        widget_bp = unreal.EditorAssetLibrary.load_asset(EUW_ASSET_PATH)
    if widget_bp is None:
        # Asset registry may not have scanned plugin content yet.
        registry = unreal.AssetRegistryHelpers.get_asset_registry()
        registry.scan_paths_synchronous(["/ReconstructionBridge"], True)
        widget_bp = unreal.EditorAssetLibrary.load_asset(EUW_ASSET_PATH)
    if widget_bp is None:
        unreal.log_error(
            f"ReconstructionBridge: widget asset not found: {EUW_ASSET_PATH}"
        )
        return None
    subsystem = unreal.get_editor_subsystem(unreal.EditorUtilitySubsystem)
    return subsystem.spawn_and_register_tab(widget_bp)


def _make_entry(block_type):
    entry = unreal.ToolMenuEntry(
        name=ENTRY_NAME,
        type=block_type,
        owner=unreal.ToolMenuOwner(MENU_OWNER),
    )
    entry.set_label(LABEL)
    entry.set_tool_tip(TOOLTIP)
    entry.set_icon(ICON_STYLE, ICON_NAME)
    entry.set_string_command(
        unreal.ToolMenuStringCommandType.PYTHON,
        "",
        OPEN_COMMAND,
    )
    return entry


def _make_setup_entry():
    entry = unreal.ToolMenuEntry(
        name=SETUP_ENTRY_NAME,
        type=unreal.MultiBlockType.MENU_ENTRY,
        owner=unreal.ToolMenuOwner(MENU_OWNER),
    )
    entry.set_label(SETUP_LABEL)
    entry.set_tool_tip(SETUP_TOOLTIP)
    entry.set_icon(ICON_STYLE, SETUP_ICON_NAME)
    entry.set_string_command(
        unreal.ToolMenuStringCommandType.PYTHON,
        "",
        SETUP_COMMAND,
    )
    return entry


def register():
    menus = unreal.ToolMenus.get()

    tools_menu = menus.extend_menu(TOOLS_MENU)
    tools_menu.add_section(SECTION_NAME, LABEL)
    tools_menu.add_menu_entry(
        SECTION_NAME, _make_entry(unreal.MultiBlockType.MENU_ENTRY)
    )
    tools_menu.add_menu_entry(SECTION_NAME, _make_setup_entry())

    toolbar = menus.extend_menu(TOOLBAR_MENU)
    toolbar.add_section(SECTION_NAME, LABEL)
    toolbar.add_menu_entry(
        SECTION_NAME, _make_entry(unreal.MultiBlockType.TOOL_BAR_BUTTON)
    )

    menus.refresh_all_widgets()
    unreal.log("ReconstructionBridge: Tools menu / toolbar entries registered")


def unregister():
    menus = unreal.ToolMenus.get()
    menus.unregister_owner_by_name(MENU_OWNER)
    menus.refresh_all_widgets()
