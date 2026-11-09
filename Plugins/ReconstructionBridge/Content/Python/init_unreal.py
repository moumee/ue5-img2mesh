# Executed automatically by the Python Editor Script Plugin at editor startup
# (every init_unreal.py on the Python path runs once).
import unreal

try:
    import reconstruction_bridge_menu

    reconstruction_bridge_menu.register()
except Exception as exc:  # never break editor startup
    unreal.log_error(f"ReconstructionBridge: failed to register menus: {exc}")
