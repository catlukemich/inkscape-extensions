import sys
import os
import re

running_in_inkscape = "Inkscape" in sys.executable
if not running_in_inkscape:
    sys.path.append("C:\\Program Files\\Inkscape\\share\\inkscape\\extensions")
    os.environ["PATH"] += "C:\\Program Files\\Inkscape\\bin"


from argparse import ArgumentParser
from typing import Any, List
import inkex
import utils
import json

class ExportIsoCurves(inkex.EffectExtension):

    def add_arguments(self, pars: ArgumentParser) -> None:
        pars.add_argument("--pages", type=str, default="")

          # Export settings
        pars.add_argument("--export_path", type=str, default="")
        pars.add_argument("--search_scope", type=str, default="auto")

        # World settings:
        pars.add_argument("--world_center", type=str, default="page")
        pars.add_argument("--custom_center_x", type=int, default=1)
        pars.add_argument("--custom_center_y", type=int, default=1)
        pars.add_argument("--tile_width", type=int, default=256)
        pars.add_argument("--tile_height", type=int, default=128)
        pars.add_argument("--vertical_step", type=int, default=128)
        pars.add_argument("--z_value", type=float, default=0.0)
        

    def effect(self) -> Any:
        # Read the paremeters:
        export_path = self.options.export_path
        search_scope = self.options.search_scope

        world_center = self.options.world_center
        if world_center == "page":
            world_center_x = self.svg.uutounit(self.svg.get("width")) / 2
            world_center_y = self.svg.uutounit(self.svg.get("height")) /  2
        if world_center == "custom":
            world_center_x = self.options.custom_center_x
            world_center_y = self.options.custom_center_y
        htw = self.options.tile_width / 2
        hth = self.options.tile_height / 2
        v_step = self.options.vertical_step
        z_value = self.options.z_value

        if not running_in_inkscape:
            selected_paths_ids = ["path58", "path44", "path3"]
            # selected_paths_ids = ["path46"]
            selected_paths = [self.svg.getElementById(path_id) for path_id in selected_paths_ids]
            # self.svg.selection.set(*selected_paths)

        # self.msg(self.options.search_scope)

        if self.options.search_scope == "auto":
            objects = self.svg.selection.values() if self.svg.selection else self.document.getroot()
        elif self.options.search_scope == "everything":
            objects = self.document.getroot()
            raise Exception("Exporting everything to paths not supported")
        else:
            objects = self.svg.selection.values()
            if len(objects) == 0: 
                self.msg("Search scope is \"selection\" but nothing selected.")
                return
        
        # All the paths that are going to be exported:
        paths = []
        # Paths related data:
        paths_data = []
        for object in objects:
            # self.msg(type(object))
            if isinstance(object, inkex.PathElement):
                label = object.get("inkscape:label")
                tags = None
                if label:
                    m = re.match(r".*\[tags=(.*)\]", label)
                    if m:
                        tags = m.group(1)

                path = object.get_path()
                paths.append(path)

                start_style = object.style.get("marker-start")
                end_style = object.style.get("marker-end")

                if not start_style:
                    start = ""
                else:
                    start = "start" if "Square" in start_style else ""

                if not end_style:
                    direction = "forward"
                    end = ""
                else:
                    direction = "forward" if "Triangle" in end_style else "reverse"
                    end = "end" if "Square" in end_style else ""

                data = {
                    "id" : object.get_id(),
                    "tags": tags,
                    "start": start,
                    "direction": direction,
                    "end": end
                }

                paths_data.append(data)

        curves_iso = []
        for i in range(len(paths)):
            path = paths[i]
            proxy_iterator = path.proxy_iterator()
            last_control_point_iso = None
            last_curve = None
            first_curve = True
            for proxy in proxy_iterator:
                control_points_iso = [utils.unproject(control_point.x - world_center_x, control_point.y - world_center_y, z_value, htw, hth, v_step) for control_point in proxy.control_points]
                control_points_flat = [{"x": control_point.x, "y": control_point.y} for control_point in proxy.control_points]

                start_letter = str(proxy)[0]
                if start_letter == "m" or start_letter == "M": # Move command
                    last_control_point_flat = control_points_flat[0]
                    last_control_point_iso = control_points_iso[0]
                    continue
                elif start_letter == "l" or start_letter == "L": # Line command
                    line_control_point_iso = control_points_iso[0]
                    curve_iso = {
                        "cp1": last_control_point_iso,
                        "cp2": last_control_point_iso,
                        "cp3": line_control_point_iso,
                        "cp4": line_control_point_iso
                    }
                    last_control_point_iso = line_control_point_iso
                    # self.msg("Line command")
                elif start_letter == "c" or start_letter == "C": # Curve command
                    cp2_iso = control_points_iso[0]
                    cp3_iso = control_points_iso[1]
                    cp4_iso = control_points_iso[2]
                    curve_iso = {
                        "cp1": last_control_point_iso,
                        "cp2": cp2_iso,
                        "cp3": cp3_iso,
                        "cp4": cp4_iso
                    }
                    last_control_point_iso = cp4_iso

                elif str(proxy).startswith("s"): # This might never happen.. might. (Strung command)
                    self.msg("::: ERROR ::: Strung command")
                else:
                    self.msg("::: ERROR ::: Something else happened, details:")
                    self.msg("The proxy is: " + str(proxy))
                    self.msg("DO YOU FUCKIN LISTENING?")

                # ERROR HANDLING
                if curve_iso["cp1"] == None:
                    self.msg("::: ERROR ::: No first control point for curve {}".format(paths_data[i]["id"]))

                if first_curve:
                    if paths_data[i]["start"] == "start":
                        curve_iso["start"] = True
                first_curve = False
                if paths_data[i]["direction"] == "forward":
                    curve_iso["forward"] = True
                else:
                    curve_iso["forward"] = False

                if paths_data[i]["tags"]:
                    curve_iso["tags"] = paths_data[i]["tags"]

                curves_iso.append(curve_iso)
                last_curve = curve_iso
            
            if paths_data[i]["end"]:
                last_curve["end"] = paths_data[i]["end"]

        # Write the curves:
        with open(export_path, "w") as file:
            json.dump(curves_iso, file, indent=2)




if __name__ == "__main__":
    extension = ExportIsoCurves()
    if running_in_inkscape:
        extension.run()
    else:
        extension.run([
            "D:/SREM/working/world.svg", 
            "--output=" +  "testassets/world_changed.svg ",
            "--export_path=C:\\tmp\\inkscape_exports\\curves.json"
        ])
