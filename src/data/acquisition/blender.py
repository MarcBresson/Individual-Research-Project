from pathlib import Path
from numpy import deg2rad
import pandas as pd
import bpy
from math import radians, sin, cos, log, atan, tan


class TransverseMercator:
    """
    see conversion formulas at
    http://en.wikipedia.org/wiki/Transverse_Mercator_projection
    and
    http://mathworld.wolfram.com/MercatorProjection.html
    """
    radius = 6378137

    def __init__(self, lat: float = 0, lon: float = 0, scale: float = 1):
        self.lat = radians(lat)
        self.lon = radians(lon)
        self.scale = scale

    def from_geographic(self, lat: float, lon: float):
        lat = radians(lat)
        lon = radians(lon) - self.lon

        B = sin(lon) * cos(lat)

        x = 0.5 * self.scale * self.radius * log((1 + B) / (1 - B))
        y = self.scale * self.radius * (atan(tan(lat) / cos(lon)) - self.lat)

        return x, y


def read_data(dataset: Path):
    data = pd.read_feather(dataset)

    for _, row in data.iterrows():
        yield row[["image_id", "lon", "lat", "computed_altitude", "computed_compass_angle"]]


def create_camera(
    width: int = 2048,
    aspect_ratio: float = 2
):
    # clear any existing camera
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.object.select_by_type(type='CAMERA')
    bpy.ops.object.delete()

    bpy.context.scene.render.engine = 'CYCLES'

    bpy.ops.object.camera_add(
        location=(0, 0, 0),
        rotation=(0, 0, 0)
    )
    camera = bpy.context.object

    camera.data.type = 'PANO'
    camera.data.cycles.panorama_type = 'EQUIRECTANGULAR'
    camera.data.cycles.panorama_resolution = width

    bpy.context.view_layer.objects.active = camera
    bpy.context.scene.camera = camera

    bpy.context.scene.render.resolution_x = width
    bpy.context.scene.render.resolution_y = int(width / aspect_ratio)

    bpy.context.scene.render.image_settings.file_format = 'JPEG'


def render_equirectangle_streetview(
    xyz: tuple[float, float, float],
    computed_compass_angle: float,
    layers_to_render: list[str],
    savepath: Path
):
    """
    Parameters
    ----------
    xyz : tuple[float, float, float]
        in meters
    computed_compass_angle : float
        in degree
    """
    camera = bpy.context.scene.camera
    camera.location = xyz
    camera.rotation_euler = mapillary_to_euler(computed_compass_angle)

    for layer_name in layers_to_render:
        select_pass(layer_name)

        savepath_layer = savepath.with_stem(f"{savepath.stem}_{layer_name}").with_suffix(".jpg")
        bpy.context.scene.render.filepath = str(savepath_layer)

        bpy.ops.render.render(write_still=True)


def init_node_tree():
    bpy.context.scene.use_nodes = True

    tree = bpy.context.scene.node_tree

    rl_node = tree.nodes.new("CompositorNodeRLayers")
    rl_node.location = (0, 0)
    rl_node.name = "RenderLayers"
    composite_node = tree.nodes.new("CompositorNodeComposite")
    composite_node.location = (400, 0)
    composite_node.name = "Composite"


def select_pass(pass_name: str):
    tree = bpy.context.scene.node_tree

    rl_node = tree.nodes.get("RenderLayers")
    composite_node = tree.nodes.get("Composite")

    render_pass = rl_node.outputs[pass_name]
    tree.links.new(render_pass, composite_node.inputs[0])


def clean_nodes():
    tree = bpy.context.scene.node_tree

    for node in tree.nodes:
        tree.nodes.remove(node)


# def mapillary_to_euler(mapillary_rotation: tuple[float, float, float]) -> tuple[float, float, float]:
#     roll, pitch, yaw = mapillary_rotation
#     euler_rotation = mathutils.Euler((pitch, yaw, roll), 'XYZ')

#     return euler_rotation


# def mapillary_to_euler(mapillary_rotation: tuple[float, float, float]) -> tuple[float, float, float]:
#     length = np.linalg.norm(mapillary_rotation)
#     euler_rotation = Matrix.Rotation(length, 3, mapillary_rotation).to_euler("XYZ")

#     return euler_rotation


def mapillary_to_euler(compass_orientation: float) -> tuple[float, float, float]:
    euler_rotation = [90, 0, -compass_orientation]

    return deg2rad(euler_rotation)


# render_pass_names = ["Depth", "Normal", "DiffCol"]

# def main():
#     clean_nodes()
#     init_node_tree(layers_to_render)
#     create_camera()

#     dataset_path = Path(r"C:\Users\marco\Documents\Cours\Individual Research Project - IRP\code\data\dataset.arrow")
#     savedir = Path(r"C:\Users\marco\Documents\Cours\Individual Research Project - IRP\code\data\blender")

#     scene = bpy.context.scene
#     projection = TransverseMercator(lat=scene["lat"], lon=scene["lon"])

#     for i, view_data in enumerate(read_data(dataset_path)):
#         image_id, lon, lat, alt, computed_compass_angle, rot_x, rot_y, rot_z = view_data

#         x, y = projection.from_geographic(lat, lon)
#         z = alt + 0.3

#         savepath: Path = savedir / str(image_id)

#         render_equirectangle_streetview((x, y, z), computed_compass_angle, layers_to_render, savepath)


def create_nodes(tmp_dir: Path, render_pass_names: list[str]) -> list[str]:
    """
    create the node tree to save each pass in a different folder.

    Parameters
    ----------
    render_pass_names : list[str]
        list of the render passes to save

    Returns
    -------
    list[str]
        path to where the passes are saved.
    """
    tree = bpy.context.scene.node_tree

    for node in tree.nodes:
        tree.nodes.remove(node)

    renderlayers_node = tree.nodes.new("CompositorNodeRLayers")
    renderlayers_node.location = (0, 0)
    renderlayers_node.name = "RenderLayers"

    save_dirs = [""] * len(render_pass_names)

    for i, render_pass_name in enumerate(render_pass_names):
        fileoutput_node = tree.nodes.new("CompositorNodeOutputFile")
        fileoutput_node.location = (400, -120 * i)
        fileoutput_node.name = render_pass_name

        save_dirs[i] = tmp_dir / render_pass_name
        fileoutput_node.base_path = str(save_dirs[i])

        render_pass = renderlayers_node.outputs[render_pass_name]
        tree.links.new(render_pass, fileoutput_node.inputs[0])

    return save_dirs


def place_camera(
    xyz: tuple[float, float, float],
    computed_compass_angle: float,
    offset_altitude: float = 0.3
):
    """
    Parameters
    ----------
    xyz : tuple[float, float, float]
        in meters
    computed_compass_angle : float
        in degree
    offset_altitude : float
        move the z point up or down to account for streets not being at 0
    """
    camera = bpy.context.scene.camera

    x, y, z = xyz
    camera.location = (x, y, z + offset_altitude)
    camera.rotation_euler = mapillary_to_euler(computed_compass_angle)


def move_render_passes(save_dirs: Path, output_dir: Path):
    image_id = output_dir.stem

    for dir_ in save_dirs:
        pass_img_path: Path = list(dir_.glob("*.*"))[0]
        pass_name = pass_img_path.parent.stem

        new_filepath = output_dir.with_stem(f"{image_id}_{pass_name}").with_suffix(".jpg")
        pass_img_path.rename(new_filepath)


def main2():
    render_pass_names = ["Depth", "Normal", "DiffCol"]

    root_dir = Path(r"C:\Users\marco\Documents\Cours\Individual Research Project - IRP\code\data")

    tmp_dir = root_dir / "tmp"
    dataset_path = root_dir / "dataset.arrow"
    savedir = root_dir / "blender"

    create_camera()
    save_dirs = create_nodes(tmp_dir, render_pass_names)

    scene = bpy.context.scene
    projection = TransverseMercator(lat=scene["lat"], lon=scene["lon"])

    for streetview_data in read_data(dataset_path):
        image_id, lon, lat, alt, computed_compass_angle = streetview_data

        x, y = projection.from_geographic(lat, lon)
        place_camera((x, y, alt), computed_compass_angle)

        bpy.ops.render.render(write_still=True)

        move_render_passes(save_dirs, savedir / image_id)
