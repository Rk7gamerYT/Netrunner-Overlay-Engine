import sys

import dearpygui.dearpygui as dpg

from engine import resource_path
from ui.dashboard import DashboardApp


def main():
    dpg.create_context()

    icon = resource_path("assets/netrunner.ico")

    dpg.create_viewport(
        title="Netrunner Overlay Engine v1.2.0",
        width=1540,
        height=960,
        min_width=1180,
        min_height=720,
        small_icon=icon,
        large_icon=icon,
        vsync=True,
    )

    dashboard = DashboardApp()
    dashboard.build()

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("primary_window", True)
    dpg.set_exit_callback(dashboard.shutdown)

    try:
        while dpg.is_dearpygui_running():
            dashboard.tick()
            dpg.render_dearpygui_frame()
    finally:
        dashboard.shutdown()
        dpg.destroy_context()


if __name__ == "__main__":
    main()
