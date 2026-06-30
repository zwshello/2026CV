from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    bridge_config_arg = DeclareLaunchArgument(
        "bridge_config",
        default_value=PathJoinSubstitution(
            [FindPackageShare("low_altitude_bringup"), "config", "gz_bridge_clock.yaml"]
        ),
        description="Path to the ros_gz_bridge YAML config file used for non-image topics.",
    )

    image_topic_arg = DeclareLaunchArgument(
        "image_topic",
        default_value="/camera/image_raw",
        description="ROS 2 image topic name after bridging from Gazebo.",
    )

    gz_image_topic_arg = DeclareLaunchArgument(
        "gz_image_topic",
        default_value="/world/baylands/model/x500_gimbal_0/link/camera_link/sensor/camera/image",
        description="Gazebo Transport camera topic bridged into ROS 2 with ros_gz_image.",
    )

    bridge_node = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        name="low_altitude_bridge",
        output="screen",
        parameters=[
            {
                "config_file": LaunchConfiguration("bridge_config"),
            }
        ],
    )

    # 用 ros_gz_bridge 直接桥接 Gazebo 相机话题到 ROS,
    # 取代旧的 low_altitude_bringup/gz_camera_bridge (Python),
    # 更稳定且零额外依赖.
    image_bridge_node = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        name="gazebo_camera_bridge",
        output="screen",
        arguments=[
            [LaunchConfiguration("gz_image_topic"), "@sensor_msgs/msg/Image[gz.msgs.Image"],
        ],
        remappings=[
            (LaunchConfiguration("gz_image_topic"), LaunchConfiguration("image_topic")),
        ],
    )

    return LaunchDescription(
        [
            bridge_config_arg,
            image_topic_arg,
            gz_image_topic_arg,
            bridge_node,
            image_bridge_node,
        ]
    )
