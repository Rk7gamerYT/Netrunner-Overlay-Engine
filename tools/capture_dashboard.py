import os
import sys

import dearpygui.dearpygui as dpg


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ui.dashboard import DashboardApp


output = os.path.join(ROOT, "dashboard-preview.png")

dpg.create_context()
dpg.create_viewport(title="Netrunner v1.2.0 Preview", width=1540, height=960)
app = DashboardApp()
app.build()
dpg.setup_dearpygui()
dpg.show_viewport()
dpg.set_primary_window("primary_window", True)

for frame in range(40):
    app.tick()
    dpg.render_dearpygui_frame()
    if frame == 20:
        dpg.output_frame_buffer(file=output)

app.shutdown()
dpg.destroy_context()
print(output)
