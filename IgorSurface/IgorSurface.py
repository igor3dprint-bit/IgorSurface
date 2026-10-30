"""IgorSurface add-in entry point."""
from .lib import ui
from .commands.fitSurface import entry as fit_surface
from .commands.planeSketch import entry as plane_sketch
from .commands.stitch import entry as stitch
from .commands.quadPatch import entry as quad_patch
from .commands.saveExport import entry as save_export
from .commands.organize import entry as organize
from .commands.freeform import entry as freeform
from .commands.autoSurface import entry as auto_surface
from .commands.generative import entry as generative
from .commands.deviation import entry as deviation
from .commands.scanTools import entry as scan_tools
from .commands.help import entry as help_cmd

COMMANDS = (scan_tools, quad_patch, freeform, auto_surface, generative, stitch,
            fit_surface, plane_sketch, deviation, organize, save_export, help_cmd)

def run(context):
    try:
        for c in COMMANDS:
            c.start()
    except Exception:
        ui.error('IgorSurface não iniciou')

def stop(context):
    try:
        for c in COMMANDS:
            c.stop()
        ui.remove_panels()
    except Exception:
        ui.error('IgorSurface não parou direito')
