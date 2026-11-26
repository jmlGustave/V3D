from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, SetParameter


def generate_launch_description():
    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time',
        default_value='true',
        description='Usar /clock publicado por Isaac Sim para el tiempo de simulación.'
    )

    launch_teleop_arg = DeclareLaunchArgument(
        'launch_teleop',
        default_value='false',
        description='Lanzar teleop_twist_keyboard en ventana xterm (requiere xterm y X11).'
    )

    set_sim_time = SetParameter(
        name='use_sim_time',
        value=LaunchConfiguration('use_sim_time')
    )

    startup_notice = LogInfo(
        msg=[
            'tfg_ros2_core iniciado con use_sim_time=',
            LaunchConfiguration('use_sim_time'),
            ', launch_teleop=',
            LaunchConfiguration('launch_teleop'),
            '.'
        ]
    )

    teleop_node = Node(
        package='teleop_twist_keyboard',
        executable='teleop_twist_keyboard',
        name='teleop_twist_keyboard',
        output='screen',
        prefix='xterm -e',
        condition=IfCondition(LaunchConfiguration('launch_teleop')),
    )

    return LaunchDescription([
        use_sim_time_arg,
        launch_teleop_arg,
        set_sim_time,
        startup_notice,
        teleop_node,
    ])