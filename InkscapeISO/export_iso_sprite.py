import sys
import os

running_in_inkscape = "Inkscape" in sys.executable
if not running_in_inkscape:
    sys.path.append("C:\\Program Files\\Inkscape\\share\\inkscape\\extensions")
    os.environ["PATH"] += "C:\\Program Files\\Inkscape\\bin"

import math
import subprocess
import tempfile
import json
from argparse import ArgumentParser
from typing import Any
import inkex
import lxml
import utils

ISO_ORIGIN_TITLE = "ISO ORIGIN"

class ExportIsoSprite(inkex.EffectExtension):

    def add_arguments(self, pars: ArgumentParser) -> None:
        pars.add_argument("--pages", type=str, default=0)

        # Export settings
        pars.add_argument("--export_path", type=str, default="")
        pars.add_argument("--search_scope", type=str, default="auto")
        pars.add_argument("--export_dpi", type=float, default=96.0)

        # World settings:
        pars.add_argument("--world_center", type=str, default="page")
        pars.add_argument("--custom_center_x", type=int, default=1)
        pars.add_argument("--custom_center_y", type=int, default=1)
        pars.add_argument("--tile_width", type=int, default=256)
        pars.add_argument("--tile_height", type=int, default=128)
        pars.add_argument("--vertical_step", type=int, default=128)
        pars.add_argument("--default_z", type=float, default=0.0)


    def effect(self) -> Any:
        export_path = self.options.export_path
        if not os.path.exists(export_path):
            os.mkdir(export_path)
            self.debug("Creating directory: " + export_path)

        if self.options.search_scope == "auto":
            nodes = self.svg.selection.values() if self.svg.selection else self.document.getroot()
        elif self.options.search_scope == "everything":
            nodes = self.document.getroot()
        else:
            nodes = self.svg.selection.values()
            if len(nodes) == 0: 
                self.msg("Search scope is \"selection\" but nothing selected.")
                return

        # Assemble all the groups, their ids :
        groups = {} # A map from group id to a group
        origins = {} # A map from group id to it's iso origin 
        def add_group_id(group):
            group_id = group.get_id()
            groups[group_id] = group

        for node in nodes:
            self.visit_node(node, add_group_id)

        groups_names_counts = {}
        for group in groups.values():
            group.name = self.get_group_name(groups_names_counts, group)
            group.layer_name = self.get_object_layer_name(group)

        # Find the origins:
        for group_id, group in groups.items():
            origin = self.get_iso_origin(group)
            origins[group_id] = origin

        # Hide all origins:
        origins_styles = {}
        for origin in origins.values():
            origins_styles[origin] = origin.attrib["style"]
            origin.attrib["style"] = "display: none"

        bboxes = utils.get_bounding_boxes(self.document, list(groups.keys()))

        # Write spr files:
        for group_id, group in groups.items():
            bbox = bboxes[group_id]
            origin = origins[group_id]
            self.write_spr_file(group, bbox, origin)

        # Export the images of groups:
        self.export_groups(groups)

        # Restore origins visibilities:
        for group in groups.values():
            group = groups[group_id]
            origin = self.get_iso_origin(group)
            origin.attrib["style"] = origins_styles[origin]
        return



    def visit_node(self, node, visitor_func):
        if isinstance(node, inkex.Group):
            group = node
            if self.group_is_iso(group):
                visitor_func(group)
                
            else:
                children = group.iterchildren()
                for child in children:
                    self.visit_node(child, visitor_func)
            return


    def get_group_name(self, groups_names_counts, group):
        group_name = group.get("inkscape:label") or group.get_id()
        number_suffix = ""
        if group_name in groups_names_counts:
            groups_names_counts[group_name] += 1
            number_suffix = "#%d" % (groups_names_counts[group_name])
        else:    
            groups_names_counts[group_name] = 1
        group_name += number_suffix
        return group_name
    

    def get_object_layer_name(self, object):
        ancestors = object.ancestors()
        layer = ancestors[len(ancestors) - 2]
        return layer.get("inkscape:label")


    def write_spr_file(self, group, bbox, origin):
        # Set up the variables:
        htw = self.options.tile_width / 2
        hth = self.options.tile_height / 2
        v_step = self.options.vertical_step

        # Find out the spatial data:
        world_center = self.options.world_center
        if world_center == "page":
            world_center_x = self.svg.uutounit(self.svg.get("width")) / 2
            world_center_y = self.svg.uutounit(self.svg.get("height")) /  2
        if world_center == "custom":
            world_center_x = self.options.custom_center_x
            world_center_y = self.options.custom_center_y

        # WolframAlpha solution path:
        # solve a = x * p - y * p , b = x * q + y * q  - z * r for x
        # => y = x - a/p
        # => solve  b = x * q + (x - a/p) * q - z * r for x
        # => x = (a*q + b*p + p*r*z) / (2 * p * q)
        # => y = x - a/p
        # Where:
        # a - the x coordinate of the origin on the canvas
        # b - the y coordinate of the origin on the canvas
        # x - the iso_x
        # y - the iso_y
        # z - the iso_z (default_z)
        # p - half tile width
        # q - half tile height
        # r - vertical step

        position_x = origin.x - world_center_x
        position_y = origin.y - world_center_y

        # Z component
        iso_z = None
        origin_data = origin.get("inkscape:label") or origin.get_id()
        z_start = origin_data.find("Z=")
        if z_start != -1:
            z_end = len(origin_data) - 1
            iso_z = float(origin_data[z_start + 2: z_end])
        iso_z = iso_z or self.options.default_z

        # Find the location of the iso sprite:
        location = utils.unproject(position_x, position_y, iso_z, htw, hth, v_step)


        def clamp(value, min, max):
            if value < min: return min
            if value > max: return max
            return value

        x = bbox.x
        y = bbox.y

        # TODO: Perhaps do clamping - but PERHAPS.
        anchor_x = (origin.x - x) / bbox.width
        anchor_y = (origin.y - y) / bbox.height
        anchor = {"anchorX": anchor_x, "anchorY": anchor_y}

        size = {
            "width": math.ceil((self.options.export_dpi / 96.0) * bbox.width),
            "height": math.ceil((self.options.export_dpi / 96.0) * bbox.height),
        }

      
        # Write the sprite description (.spr) file:
        declaration_filename = self.options.export_path + os.sep + group.name + ".spr"
        with open(declaration_filename, "w") as f:
            sprite = {
                "name": group.name,
                "layer_name": group.layer_name,
                "image": group.name + ".png",
                "location": location,
                "anchor": anchor,
                "size": size
            }
            json.dump(sprite, f, indent = 2)
        


    def export_groups(self, groups):
        export_directory = self.options.export_path

        groups_ids = []
        for group in groups.values():
            groups_ids.append(group.get_id())

        actions = []
        for group in groups.values():
            actions.append("export-id:%s" % group.get_id())
            actions.append("export-id-only")    
            actions.append("export-filename:%s" % (export_directory + os.sep + group.name + ".png"))
            actions.append("export-do")

        utils.inkscape(self.document, "--actions=\"%s\"" % "; ".join(actions)  + " --export-dpi={}".format(self.options.export_dpi), use_cmd=True)          

        # TODO: Display the export report:
        # self.msg("Exported group with id:\"%s\" and name: \"%s\"" % (group.get_id(), group_name))
        # self.msg("Saved filename: \"" + filename_name + ".png\"")


    def group_is_iso(self, group):
        for child in group.iterchildren():
            id = child.get_id()
            if f"[{ISO_ORIGIN_TITLE}]" in id:
                return True
        return False

    def get_iso_origin(self, iso_group):
        origin = None
        for child in iso_group.iterchildren():
            id = child.get_id()
            if f"[{ISO_ORIGIN_TITLE}]" in id:
                origin = child
                break
        
        if origin is None:
            return None

        # Calculate the origin absolute position:
        group_transform = iso_group.composed_transform()
        origin_bbox = origin.bounding_box(group_transform)
        origin_bbox_center_pixels = (
            self.svg.uutounit(origin_bbox.center_x),
            self.svg.uutounit(origin_bbox.center_y)
        )
        origin_x = origin_bbox_center_pixels[0]
        origin_y = origin_bbox_center_pixels[1]
        origin.x = origin_x
        origin.y = origin_y

        return origin



if __name__ == '__main__':
    extension = ExportIsoSprite()
    if running_in_inkscape:
        extension.run()
    else:
        extension.run([
            "D:/SREM/working/world.svg", 
            "--output=" +  "testassets/world_changed.svg ",
            "--export_path=C:\\tmp\\inkscape_exports"
        ])
