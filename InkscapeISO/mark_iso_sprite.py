import sys
import os

running_in_inkscape = "Inkscape" in sys.executable
if not running_in_inkscape:
    sys.path.append("C:\\Program Files\\Inkscape\\share\\inkscape\\extensions")
    os.environ["PATH"] += "C:\\Program Files\\Inkscape\\bin"

from argparse import ArgumentParser
from typing import Any
import inkex
import utils

ISO_ORIGIN_TITLE = "ISO ORIGIN"

class MarkIsoSprite(inkex.EffectExtension):

    def add_arguments(self, pars: ArgumentParser) -> None:
        pars.add_argument("--origin_location", type=int, default=5) # Default is center
        pars.add_argument("--show_origin", type=bool, default=True)
        pars.add_argument("--z_value", type=float, default=0.0)

    def effect(self) -> Any:
        if not running_in_inkscape:
            floor2 = self.svg.getElementById("g2511")
            window_w = self.svg.getElementById("g60")
            self.svg.selection.set(window_w)

        if len(self.svg.selection) == 0: 
            self.debug("Nothing selected, cancelling")
            return
        
        nodes_to_mark = []
        for i in range(0, len(self.svg.selection)):
            object = self.svg.selection[i]
            if isinstance(object, inkex.Group):
                nodes_to_mark.append(object)

        marked = False
        for group in nodes_to_mark:
            self.mark_iso_sprite(group)
            marked = True
            
        if not marked:
            self.msg("No groups selected, nothing to mark.")

    def mark_iso_sprite(self, group):
        # Remove the old origin if present:
        for child in group.iterchildren():
            name = child.get("inkscape:label")
            if name is None: continue
            if f"[{ISO_ORIGIN_TITLE}]" in name:
                group.remove(child) # Remove the old origin

        # Find the next number of iso origin
        root = self.svg.getroottree().getroot()
        number = 0
        for element in root.iter():
            name = element.get("inkscape:label")
            if name is None: continue
            if f"[{ISO_ORIGIN_TITLE}]" in name:
                number += 1

        iso_origin_name = "[%s][#%d][Z=%.4f]"  % (ISO_ORIGIN_TITLE, number, self.options.z_value)

        # Create and position the new origin:
        iso_origin = inkex.elements.Circle.new(inkex.Vector2d(0,0), 1) # The circle that will mark the isometric origin
        iso_origin.set_id(iso_origin_name)
        iso_origin.set("inkscape:label", iso_origin_name)

        # Make the origin visible/invisible regarding user's choice:
        if self.options.show_origin:
            iso_origin.attrib["style"] = "display:inline"
        else:
            iso_origin.attrib["style"] = "display:none"

        # Do the changes and reload the SVG:
        self.svg.selection.set(iso_origin, group)

        # self.center_iso_origin_1(group, iso_origin) 
        self.position_iso_origin(group, iso_origin)
        
        # Append the origin to the group:
        group.append(iso_origin)

        return None # This get's ignored whatsoever by the ExtensionBase.

    def position_iso_origin(self, group, iso_origin):
        iso_origin.attrib['r'] =  "4px"
        iso_origin.style['fill'] = "#ff0000"

        absolute_position = self.get_origin_absolute_position(group)
        translation_transform = inkex.Transform(translate=absolute_position)
        try:
            parent_transform = group.composed_transform()
        except AttributeError:
            self.debug("ATTRIBUTE ERROR")
            pass
        else:
            transform = -parent_transform @ translation_transform

        iso_origin.transform = transform

    def get_origin_absolute_position(self, group):
        # Calculate the new position of origin (this is not accurate, because the bounds are not visual bounds in the inkscape's language):
        parent_transform = inkex.Transform()
        parent = group.getparent()
        if parent is not None:
            parent_transform = parent.composed_transform()
        bbox = group.bounding_box(parent_transform)

        center_x = 0
        center_y = 0

        selected_origin = self.options.origin_location
        if selected_origin == 1:
            center_x = bbox.left
            center_y = bbox.top
        elif selected_origin == 2:
            center_x = bbox.center_x
            center_y = bbox.top
        elif selected_origin == 3:
            center_x = bbox.right
            center_y = bbox.top
        elif selected_origin == 4:
            center_x = bbox.left
            center_y = bbox.center_y
        elif selected_origin == 5:
            center_x = bbox.center_x
            center_y = bbox.center_y
        elif selected_origin == 6:
            center_x = bbox.right
            center_y = bbox.center_y
        elif selected_origin == 7:
            center_x = bbox.left
            center_y = bbox.bottom
        elif selected_origin == 8:
            center_x = bbox.center_x
            center_y = bbox.bottom
        elif selected_origin == 9:
            center_x = bbox.right
            center_y = bbox.bottom
        
        return (center_x, center_y)


    

if __name__ == '__main__':
    extension = MarkIsoSprite()
    if running_in_inkscape:
        extension.run()
    else:
        extension.run(["testassets/world.svg", "--output=" +  "testassets/world_changed.svg"])

    