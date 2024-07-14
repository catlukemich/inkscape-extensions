import os
import sys
import copy
import tempfile
import inkex
import subprocess


def unproject(position_x, position_y, iso_z, htw, hth, v_step):
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

        # Find the location of the document space 2d point (position_x, position_y):
        # Z component
        # X and Y components - see above for the solution.
        iso_x = (position_x * hth + position_y * htw + hth * v_step * iso_z) / (2 * htw * hth)
        iso_y = iso_x - position_x / htw
        location = {"x": iso_x, "y": iso_y, "z": iso_z}
        return location



# Make a copy of SVG document
def write_document(document):
    copied = copy.deepcopy(document)
    with tempfile.NamedTemporaryFile(delete=False) as temporary_file:
        copied.write(temporary_file)
        return temporary_file.name
        
def write_svg(svg, *filename):
    """Writes an svg to the given filename"""
    filename = os.path.join(*filename)
    with open(filename, "wb") as fhl:
        if isinstance(svg, inkex.elements.SvgDocumentElement):
            svg = inkex.elements.ElementTree(svg)
        if hasattr(svg, "write"):
            # XML document
            svg.write(fhl)
        elif isinstance(svg, bytes):
            fhl.write(svg)
        else:
            raise ValueError("Not sure what type of SVG data this is.")
    return filename

def call(program, *args, **kwargs):
    
    subprocess_args = (program,) + args

    # This is due to the issue: https://gitlab.com/inkscape/inkscape/-/issues/4875
    if "use_cmd" in kwargs and kwargs["use_cmd"]:
        call_args = "echo %s %s | cmd" % (program, " ".join(args))
        result = subprocess.run(call_args, shell=True, capture_output=True)
        return result
    else:
        with subprocess.Popen(
            subprocess_args,
            stdout=subprocess.PIPE,  # Grab any output (return it)
            stderr=subprocess.PIPE,  # Take all errors, just incase
            **kwargs,
        ) as process:
            (stdout, stderr) = process.communicate()
            if process.returncode == 0:
                if isinstance(stdout, bytes):
                    return stdout.decode(sys.stdout.encoding or "utf-8")
            raise inkex.command.ProgramRunError(program, process.returncode, stderr, stdout, args)

# This is also messed up in the inkex API.
def inkscape(svg, *args, **kwargs):
    with tempfile.NamedTemporaryFile(prefix="inkscape_call", delete=False) as tmpfile:
        svg_file = write_svg(svg, "", tmpfile.name)
        stdout = call("inkscape.exe", svg_file, *args, **kwargs)
        return stdout

def get_bounding_boxes(document, groups_ids):
    arg1 = "--query-id=%s" % (",".join(groups_ids))
    arg2 = "--query-x" 
    arg3 = "--query-y"
    arg4 = "--query-width"
    arg5 = "--query-height"
    ret = inkscape(document, arg1, arg2, arg3, arg4, arg5)

    lines = ret.split("\n")
    xs_strs = lines[0].split(",")
    ys_strs = lines[1].split(",")
    widths_strs = lines[2].split(",")
    heights_strs = lines[3].split(",")

    class BoundingBox:
        def __init__(self, x, y, w, h):
            self.x = x
            self.y = y
            self.width = w
            self.height = h

        def __str__(self) -> str:
            return "(%.4f, %.4f, %.4f, %.4f)" % (self.x, self.y, self.width, self.height)

    num_groups = len(groups_ids)
    bboxes_dict = {}
    for i in range(0, num_groups):
        group_id = groups_ids[i]
        x = float(xs_strs[i])
        y = float(ys_strs[i])
        width = float(widths_strs[i])
        height = float(heights_strs[i])
        bbox = BoundingBox(x, y, width, height)
        bboxes_dict[group_id] = bbox

    return bboxes_dict
