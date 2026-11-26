from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node, SetParameter
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    """Genera el LaunchDescription para monitorizar el par estéreo y ground truth."""
    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time',
        default_value='true',
        description='Usar /clock publicado por Isaac Sim para el tiempo de simulación.'
    )

    record_gt_arg = DeclareLaunchArgument(
        'record_gt',
        default_value='false',
        description='Activar registro de trayectoria ground truth en formato TUM.'
    )

    use_rviz_arg = DeclareLaunchArgument(
        'use_rviz',
        default_value='true',
        description='Lanzar RViz2 con la configuración de monitorización estéreo.'
    )

    odom_topic_arg = DeclareLaunchArgument(
        'odom_topic',
        default_value='/ground_truth/odom',
        description='Tópico nav_msgs/msg/Odometry para tum_trajectory_logger.'
    )

    output_file_arg = DeclareLaunchArgument(
        'output_file',
        default_value='trajectory_gt.tum',
        description='Ruta del archivo TUM de salida para tum_trajectory_logger.'
    )

    set_sim_time = SetParameter(
        name='use_sim_time',
        value=LaunchConfiguration('use_sim_time')
    )

    rviz_config_path = PathJoinSubstitution([
        FindPackageShare('tfg_ros2_core'),
        'config',
        'tfg_monitor.rviz'
    ])

    startup_notice = LogInfo(
        msg=[
            'step1_monitor iniciado con use_sim_time=',
            LaunchConfiguration('use_sim_time'),
            ', record_gt=',
            LaunchConfiguration('record_gt'),
            ', use_rviz=',
            LaunchConfiguration('use_rviz'),
            '.'
        ]
    )

    stereo_sync_monitor_node = Node(
        package='tfg_ros2_core',
        executable='stereo_sync_monitor',
        name='stereo_sync_monitor',
        output='screen',
        parameters=[
            {
                'use_sim_time': ParameterValue(
                    LaunchConfiguration('use_sim_time'),
                    value_type=bool
                )
            }
        ]
    )

    tum_trajectory_logger_node = Node(
        package='tfg_ros2_core',
        executable='tum_trajectory_logger',
        name='tum_trajectory_logger',
        output='screen',
        parameters=[
            {
                'use_sim_time': ParameterValue(
                    LaunchConfiguration('use_sim_time'),
                    value_type=bool
                ),
                'odom_topic': ParameterValue(
                    LaunchConfiguration('odom_topic'),
                    value_type=str
                ),
                'output_file': ParameterValue(
                    LaunchConfiguration('output_file'),
                    value_type=str
                ),
            }
        ],
        condition=IfCondition(LaunchConfiguration('record_gt'))
    )

    rviz2_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        arguments=['-d', rviz_config_path],
        parameters=[
            {
                'use_sim_time': ParameterValue(
                    LaunchConfiguration('use_sim_time'),
                    value_type=bool
                )
            }
        ],
        condition=IfCondition(LaunchConfiguration('use_rviz'))
    )

    return LaunchDescription([
        use_sim_time_arg,
        record_gt_arg,
        use_rviz_arg,
        odom_topic_arg,
        output_file_arg,
        set_sim_time,
        startup_notice,
        stereo_sync_monitor_node,
        tum_trajectory_logger_node,
        rviz2_node,
    ])
