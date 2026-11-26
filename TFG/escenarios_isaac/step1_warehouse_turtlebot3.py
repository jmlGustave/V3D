#!/usr/bin/env python3
"""Escena Standalone de Isaac Sim 6.2 para validar el Paso 1 con ROS 2 Humble.

Abre por defecto /isaac-workspace/entorno_1.usd (si existe, con la fábrica y el
TurtleBot3 ya colocados) o carga Simple Warehouse + tb3_burger_processed.usda
desde Nucleus, añade el par estéreo 1280x720 a 30 Hz (baseline 0.08 m) y monta
el Action Graph de isaacsim.ros2.bridge para:
  - /clock
  - /camera/left/{image_raw,camera_info} y /camera/right/{image_raw,camera_info}
  - /tf (odom -> base_link -> camera_left_link / camera_right_link)
  - /ground_truth/odom
  - /cmd_vel (controlador diferencial)
"""

import argparse
import os
import sys

from isaacsim import SimulationApp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Escena Isaac Sim 6.2 (entorno_1.usd / Warehouse + TurtleBot3 + ROS 2 Bridge)."
    )
    parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Ejecutar sin ventana gráfica (por defecto True; usa --no-headless para GUI).",
    )
    parser.add_argument(
        "--scene",
        type=str,
        default="/isaac-workspace/entorno_1.usd",
        help="Escena USD local a abrir si existe (pasa --scene '' para crear desde cero).",
    )
    parser.add_argument(
        "--warehouse",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Cargar Simple Warehouse si no se usa --scene local.",
    )
    parser.add_argument(
        "--baseline",
        type=float,
        default=0.08,
        help="Baseline estéreo en metros (rango objetivo 0.06-0.10; default: 0.08).",
    )
    parser.add_argument(
        "--domain-id",
        type=int,
        default=42,
        help="ROS_DOMAIN_ID para el contexto DDS (default: 42).",
    )
    parser.add_argument(
        "--turtlebot-usd",
        type=str,
        default="",
        help="Ruta USD opcional para TurtleBot3 si no está ya en la escena.",
    )
    return parser.parse_args()


ARGS = parse_args()

# SimulationApp debe instanciarse SIEMPRE antes de importar isaacsim.* u omni.*
simulation_app = SimulationApp(
    {
        "headless": ARGS.headless,
        "width": 1280,
        "height": 720,
    }
)

import carb
import omni.client
import omni.graph.core as og
import omni.usd
from isaacsim.core.api import World
from isaacsim.core.utils.extensions import enable_extension
from isaacsim.core.utils.prims import define_prim, get_prim_at_path
from isaacsim.core.utils.stage import add_reference_to_stage
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics

try:
    from isaacsim.storage.native import get_assets_root_path
except ImportError:
    from isaacsim.core.utils.nucleus import get_assets_root_path


def resolve_og_node_type(candidates: list[str]) -> str:
    """Devuelve el primer tipo de nodo OmniGraph registrado en Isaac Sim 6.2."""
    for node_type_name in candidates:
        node_type = og.get_node_type(node_type_name)
        if node_type is not None and node_type.is_valid():
            return node_type_name
    raise RuntimeError(f"Ningún tipo de nodo OmniGraph disponible entre: {candidates}")


def discover_turtlebot_usd(assets_root: str) -> list[str]:
    """Construye la lista de candidatos USD para TurtleBot3 Burger en Isaac Sim 6.2."""
    tb3_dir = f"{assets_root}/Isaac/Robots/Turtlebot/Turtlebot3"
    discovered: list[str] = [
        f"{tb3_dir}/tb3_burger_processed.usda",
    ]
    result, entries = omni.client.list(tb3_dir)
    if result == omni.client.Result.OK:
        for entry in entries:
            rel = entry.relative_path
            if rel.endswith((".usd", ".usda", ".usdc")):
                full_url = f"{tb3_dir}/{rel}"
                if full_url not in discovered:
                    discovered.append(full_url)
    discovered.extend(
        [
            f"{assets_root}/Isaac/Robots/Turtlebot/Turtlebot3/turtlebot3_burger.usd",
            f"{assets_root}/Isaac/Robots/ROBOTIS/Turtlebot3/turtlebot3_burger.usd",
        ]
    )
    return discovered


def inspect_robot_in_stage() -> tuple[str, str, list[str]]:
    """Localiza en el Stage actual la raíz de articulación, base_link y juntas de rueda."""
    stage = omni.usd.get_context().get_stage()
    articulation_root = ""
    base_link_path = ""
    revolute_joints: list[str] = []

    for prim in Usd.PrimRange(stage.GetPseudoRoot()):
        path_str = prim.GetPath().pathString
        if prim.HasAPI(UsdPhysics.ArticulationRootAPI) and not articulation_root:
            articulation_root = path_str

    if not articulation_root:
        return "", "", []

    # Determina el contenedor raíz del robot para buscar enlaces y juntas
    robot_scope = articulation_root
    art_prim = stage.GetPrimAtPath(articulation_root)
    if art_prim.GetName() in ("base_footprint", "base_link") and art_prim.GetParent():
        parent_path = art_prim.GetParent().GetPath().pathString
        if parent_path not in ("/", "/World"):
            robot_scope = parent_path

    scope_prim = stage.GetPrimAtPath(robot_scope)
    for prim in Usd.PrimRange(scope_prim):
        name = prim.GetName()
        if name == "base_link" and not base_link_path:
            base_link_path = prim.GetPath().pathString
        elif name == "base_footprint" and not base_link_path:
            base_link_path = prim.GetPath().pathString
        if prim.IsA(UsdPhysics.RevoluteJoint):
            revolute_joints.append(name)

    if not base_link_path:
        base_link_path = articulation_root

    wheel_joints = ["wheel_left_joint", "wheel_right_joint"]
    if not all(j in revolute_joints for j in wheel_joints):
        left_candidates = [j for j in revolute_joints if "left" in j.lower()]
        right_candidates = [j for j in revolute_joints if "right" in j.lower()]
        if left_candidates and right_candidates:
            wheel_joints = [left_candidates[0], right_candidates[0]]

    return articulation_root, base_link_path, wheel_joints


def create_stereo_camera(prim_path: str, translation_xyz: tuple[float, float, float]) -> None:
    """Crea o actualiza una cámara USD orientada hacia +X del chasis (+Z arriba)."""
    stage = omni.usd.get_context().get_stage()
    cam = UsdGeom.Camera.Define(stage, prim_path)
    cam.GetFocalLengthAttr().Set(24.0)
    cam.GetHorizontalApertureAttr().Set(20.955)
    cam.GetClippingRangeAttr().Set(Gf.Vec2f(0.05, 100.0))

    xform = UsdGeom.Xformable(cam.GetPrim())
    xform.ClearXformOpOrder()
    xform.AddTranslateOp().Set(Gf.Vec3d(*translation_xyz))
    # Alinea la cámara USD (-Z vista, +Y arriba) con el avance +X del robot y +Z arriba
    xform.AddRotateXYZOp().Set(Gf.Vec3f(90.0, 0.0, -90.0))


def build_ros2_action_graph(
    articulation_root_path: str,
    chassis_prim_path: str,
    left_cam_path: str,
    right_cam_path: str,
    wheel_joints: list[str],
    domain_id: int,
) -> None:
    stage = omni.usd.get_context().get_stage()
    graph_path = "/World/ROS2_Bridge"
    if stage.GetPrimAtPath(graph_path).IsValid():
        stage.RemovePrim(graph_path)

    diff_ctrl_type = resolve_og_node_type(
        [
            "isaacsim.robot.wheeled_robots.DifferentialController",
            "isaacsim.robot.wheeled_robots.nodes.DifferentialController",
            "omni.isaac.wheeled_robots.DifferentialController",
        ]
    )
    art_ctrl_type = resolve_og_node_type(
        [
            "isaacsim.core.nodes.IsaacArticulationController",
            "omni.isaac.core.nodes.IsaacArticulationController",
        ]
    )

    keys = og.Controller.Keys
    og.Controller.edit(
        {"graph_path": graph_path, "evaluator_name": "execution"},
        {
            keys.CREATE_NODES: [
                ("OnPlaybackTick", "omni.graph.action.OnPlaybackTick"),
                ("ROS2Context", "isaacsim.ros2.bridge.ROS2Context"),
                ("ReadSimTime", "isaacsim.core.nodes.IsaacReadSimulationTime"),
                ("PublishClock", "isaacsim.ros2.bridge.ROS2PublishClock"),
                ("ComputeOdom", "isaacsim.core.nodes.IsaacComputeOdometry"),
                ("PublishGtOdom", "isaacsim.ros2.bridge.ROS2PublishOdometry"),
                ("PublishOdomTF", "isaacsim.ros2.bridge.ROS2PublishRawTransformTree"),
                ("PublishRobotTF", "isaacsim.ros2.bridge.ROS2PublishTransformTree"),
                ("SubscribeTwist", "isaacsim.ros2.bridge.ROS2SubscribeTwist"),
                ("BreakLinear", "omni.graph.nodes.BreakVector3"),
                ("BreakAngular", "omni.graph.nodes.BreakVector3"),
                ("DiffController", diff_ctrl_type),
                ("ArticulationCtrl", art_ctrl_type),
                ("RenderLeft", "isaacsim.core.nodes.IsaacCreateRenderProduct"),
                ("RenderRight", "isaacsim.core.nodes.IsaacCreateRenderProduct"),
                ("CamLeftRGB", "isaacsim.ros2.bridge.ROS2CameraHelper"),
                ("CamRightRGB", "isaacsim.ros2.bridge.ROS2CameraHelper"),
                ("StereoCameraInfo", "isaacsim.ros2.bridge.ROS2CameraInfoHelper"),
            ],
            keys.SET_VALUES: [
                ("ROS2Context.inputs:domain_id", domain_id),
                ("ComputeOdom.inputs:chassisPrim", [Sdf.Path(articulation_root_path)]),
                ("PublishGtOdom.inputs:topicName", "/ground_truth/odom"),
                ("PublishGtOdom.inputs:odomFrameId", "odom"),
                ("PublishGtOdom.inputs:chassisFrameId", "base_link"),
                ("PublishOdomTF.inputs:topicName", "/tf"),
                ("PublishOdomTF.inputs:parentFrameId", "odom"),
                ("PublishOdomTF.inputs:childFrameId", "base_link"),
                ("PublishRobotTF.inputs:topicName", "/tf"),
                ("PublishRobotTF.inputs:parentPrim", [Sdf.Path(chassis_prim_path)]),
                (
                    "PublishRobotTF.inputs:targetPrims",
                    [Sdf.Path(left_cam_path), Sdf.Path(right_cam_path)],
                ),
                ("SubscribeTwist.inputs:topicName", "/cmd_vel"),
                ("DiffController.inputs:wheelRadius", 0.033),
                ("DiffController.inputs:wheelDistance", 0.160),
                ("DiffController.inputs:maxLinearSpeed", 0.22),
                ("DiffController.inputs:maxAngularSpeed", 2.84),
                ("ArticulationCtrl.inputs:targetPrim", [Sdf.Path(articulation_root_path)]),
                ("ArticulationCtrl.inputs:robotPath", articulation_root_path),
                ("ArticulationCtrl.inputs:jointNames", wheel_joints),
                ("RenderLeft.inputs:cameraPrim", [Sdf.Path(left_cam_path)]),
                ("RenderLeft.inputs:width", 1280),
                ("RenderLeft.inputs:height", 720),
                ("RenderRight.inputs:cameraPrim", [Sdf.Path(right_cam_path)]),
                ("RenderRight.inputs:width", 1280),
                ("RenderRight.inputs:height", 720),
                ("CamLeftRGB.inputs:type", "rgb"),
                ("CamLeftRGB.inputs:topicName", "/camera/left/image_raw"),
                ("CamLeftRGB.inputs:frameId", "camera_left_link"),
                ("CamRightRGB.inputs:type", "rgb"),
                ("CamRightRGB.inputs:topicName", "/camera/right/image_raw"),
                ("CamRightRGB.inputs:frameId", "camera_right_link"),
                ("StereoCameraInfo.inputs:topicName", "/camera/left/camera_info"),
                ("StereoCameraInfo.inputs:topicNameRight", "/camera/right/camera_info"),
                ("StereoCameraInfo.inputs:frameId", "camera_left_link"),
                ("StereoCameraInfo.inputs:frameIdRight", "camera_right_link"),
            ],
            keys.CONNECT: [
                # Reloj /clock
                ("OnPlaybackTick.outputs:tick", "PublishClock.inputs:execIn"),
                ("ROS2Context.outputs:context", "PublishClock.inputs:context"),
                ("ReadSimTime.outputs:simulationTime", "PublishClock.inputs:timeStamp"),
                # Ground truth /ground_truth/odom y TF odom -> base_link
                ("OnPlaybackTick.outputs:tick", "ComputeOdom.inputs:execIn"),
                ("ComputeOdom.outputs:execOut", "PublishGtOdom.inputs:execIn"),
                ("ComputeOdom.outputs:execOut", "PublishOdomTF.inputs:execIn"),
                ("ROS2Context.outputs:context", "PublishGtOdom.inputs:context"),
                ("ROS2Context.outputs:context", "PublishOdomTF.inputs:context"),
                ("ReadSimTime.outputs:simulationTime", "PublishGtOdom.inputs:timeStamp"),
                ("ReadSimTime.outputs:simulationTime", "PublishOdomTF.inputs:timeStamp"),
                ("ComputeOdom.outputs:position", "PublishGtOdom.inputs:position"),
                ("ComputeOdom.outputs:orientation", "PublishGtOdom.inputs:orientation"),
                ("ComputeOdom.outputs:linearVelocity", "PublishGtOdom.inputs:linearVelocity"),
                ("ComputeOdom.outputs:angularVelocity", "PublishGtOdom.inputs:angularVelocity"),
                ("ComputeOdom.outputs:position", "PublishOdomTF.inputs:translation"),
                ("ComputeOdom.outputs:orientation", "PublishOdomTF.inputs:rotation"),
                # TF base_link -> camera_left_link / camera_right_link
                ("OnPlaybackTick.outputs:tick", "PublishRobotTF.inputs:execIn"),
                ("ROS2Context.outputs:context", "PublishRobotTF.inputs:context"),
                ("ReadSimTime.outputs:simulationTime", "PublishRobotTF.inputs:timeStamp"),
                # Teleoperación /cmd_vel -> controlador diferencial -> ruedas
                ("OnPlaybackTick.outputs:tick", "SubscribeTwist.inputs:execIn"),
                ("ROS2Context.outputs:context", "SubscribeTwist.inputs:context"),
                ("SubscribeTwist.outputs:linearVelocity", "BreakLinear.inputs:tuple"),
                ("SubscribeTwist.outputs:angularVelocity", "BreakAngular.inputs:tuple"),
                ("BreakLinear.outputs:x", "DiffController.inputs:linearVelocity"),
                ("BreakAngular.outputs:z", "DiffController.inputs:angularVelocity"),
                ("SubscribeTwist.outputs:execOut", "DiffController.inputs:execIn"),
                (
                    "DiffController.outputs:velocityCommand",
                    "ArticulationCtrl.inputs:velocityCommand",
                ),
                ("OnPlaybackTick.outputs:tick", "ArticulationCtrl.inputs:execIn"),
                # Par estéreo 1280x720 encadenado para que ambos RenderProducts estén listos
                ("OnPlaybackTick.outputs:tick", "RenderLeft.inputs:execIn"),
                ("RenderLeft.outputs:execOut", "RenderRight.inputs:execIn"),
                ("RenderRight.outputs:execOut", "CamLeftRGB.inputs:execIn"),
                ("RenderRight.outputs:execOut", "CamRightRGB.inputs:execIn"),
                ("RenderRight.outputs:execOut", "StereoCameraInfo.inputs:execIn"),
                (
                    "RenderLeft.outputs:renderProductPath",
                    "CamLeftRGB.inputs:renderProductPath",
                ),
                (
                    "RenderRight.outputs:renderProductPath",
                    "CamRightRGB.inputs:renderProductPath",
                ),
                (
                    "RenderLeft.outputs:renderProductPath",
                    "StereoCameraInfo.inputs:renderProductPath",
                ),
                (
                    "RenderRight.outputs:renderProductPath",
                    "StereoCameraInfo.inputs:renderProductPathRight",
                ),
                ("ROS2Context.outputs:context", "CamLeftRGB.inputs:context"),
                ("ROS2Context.outputs:context", "CamRightRGB.inputs:context"),
                ("ROS2Context.outputs:context", "StereoCameraInfo.inputs:context"),
            ],
        },
    )


def main() -> None:
    enable_extension("isaacsim.robot.wheeled_robots")
    enable_extension("isaacsim.ros2.bridge")

    used_local_scene = False
    if ARGS.scene and os.path.exists(ARGS.scene):
        carb.log_info(f"Abriendo escena local guardada: {ARGS.scene}")
        omni.usd.get_context().open_stage(ARGS.scene)
        simulation_app.update()
        simulation_app.update()
        used_local_scene = True

    world = World(
        stage_units_in_meters=1.0,
        physics_dt=1.0 / 60.0,
        rendering_dt=1.0 / 30.0,
    )

    assets_root = None
    if not used_local_scene:
        assets_root = get_assets_root_path()
        if ARGS.warehouse and assets_root is not None:
            warehouse_usd = f"{assets_root}/Isaac/Environments/Simple_Warehouse/warehouse.usd"
            define_prim("/World/Warehouse", "Xform")
            add_reference_to_stage(usd_path=warehouse_usd, prim_path="/World/Warehouse")
            carb.log_info(f"Escenario cargado: {warehouse_usd}")
        else:
            world.scene.add_default_ground_plane()

    art_root, chassis_prim, wheel_joints = inspect_robot_in_stage()

    if not art_root:
        if assets_root is None:
            assets_root = get_assets_root_path()
        if assets_root is None and not ARGS.turtlebot_usd:
            carb.log_error("No se encontró TurtleBot3 en la escena ni conexión a Nucleus.")
            simulation_app.close()
            sys.exit(1)

        candidates = (
            [ARGS.turtlebot_usd] if ARGS.turtlebot_usd else discover_turtlebot_usd(assets_root)
        )
        robot_root = "/World/TurtleBot3"
        loaded_usd = ""
        for candidate in candidates:
            try:
                add_reference_to_stage(usd_path=candidate, prim_path=robot_root)
                loaded_usd = candidate
                break
            except FileNotFoundError:
                continue
        if not loaded_usd:
            carb.log_error(f"No se encontró TurtleBot3 USD en: {candidates}")
            simulation_app.close()
            sys.exit(1)
        simulation_app.update()
        art_root, chassis_prim, wheel_joints = inspect_robot_in_stage()

    if not art_root:
        carb.log_error("No se detectó ArticulationRootAPI para el TurtleBot3 en el Stage.")
        simulation_app.close()
        sys.exit(1)

    print(
        f"[TFG] Robot detectado -> articulation_root='{art_root}', "
        f"chassis='{chassis_prim}', wheels={wheel_joints}",
        flush=True,
    )

    half_b = ARGS.baseline / 2.0
    left_cam_path = f"{chassis_prim}/camera_left_link"
    right_cam_path = f"{chassis_prim}/camera_right_link"
    create_stereo_camera(left_cam_path, (0.06, half_b, 0.14))
    create_stereo_camera(right_cam_path, (0.06, -half_b, 0.14))

    build_ros2_action_graph(
        articulation_root_path=art_root,
        chassis_prim_path=chassis_prim,
        left_cam_path=left_cam_path,
        right_cam_path=right_cam_path,
        wheel_joints=wheel_joints,
        domain_id=ARGS.domain_id,
    )

    world.reset()
    print(
        f"[TFG] Simulación en marcha (escena={'entorno_1.usd' if used_local_scene else 'Nucleus'}, "
        f"headless={ARGS.headless}, baseline={ARGS.baseline:.3f} m, ROS_DOMAIN_ID={ARGS.domain_id}).",
        flush=True,
    )

    while simulation_app.is_running():
        world.step(render=True)

    simulation_app.close()


if __name__ == "__main__":
    main()
