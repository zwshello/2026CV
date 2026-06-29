"""Launch the dataset collector alongside the gz/ROS bridge.

Run this AFTER ``spawn_targets.py`` has populated the world. The collector
reads ``manifest_path`` to know what models to track for ground-truth labels
and writes the (image, label) pairs under ``output_dir``.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    image_topic_arg = DeclareLaunchArgument("image_topic", default_value="/camera/image_raw")
    camera_info_topic_arg = DeclareLaunchArgument(
        "camera_info_topic", default_value="/camera/camera_info"
    )
    gz_image_topic_arg = DeclareLaunchArgument(
        "gz_image_topic",
        default_value="/world/baylands/model/x500_gimbal_0/link/camera_link/sensor/camera/image",
    )
    manifest_path_arg = DeclareLaunchArgument(
        "manifest_path",
        default_value="/home/libo/2026CV/sim/runtime/spawned_latest.json",
    )
    output_dir_arg = DeclareLaunchArgument(
        "output_dir", default_value="/home/libo/2026CV/dataset/sim_v1"
    )
    capture_hz_arg = DeclareLaunchArgument("capture_hz", default_value="2.0")
    target_total_frames_arg = DeclareLaunchArgument(
        "target_total_frames", default_value="5000"
    )
    world_arg = DeclareLaunchArgument("world", default_value="baylands")
    camera_pose_topic_arg = DeclareLaunchArgument(
        "camera_pose_gz_topic", default_value="/world/baylands/pose/info"
    )
    camera_link_name_arg = DeclareLaunchArgument(
        "camera_link_name", default_value="x500_gimbal_0::camera_link"
    )

    bridge_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution(
                [FindPackageShare("low_altitude_bringup"), "launch", "sim_bridge.launch.py"]
            )
        ),
        launch_arguments={
            "image_topic": LaunchConfiguration("image_topic"),
            "gz_image_topic": LaunchConfiguration("gz_image_topic"),
        }.items(),
    )

    collector = Node(
        package="low_altitude_bringup",
        executable="dataset_collector",
        name="dataset_collector",
        output="screen",
        parameters=[
            {
                "image_topic": LaunchConfiguration("image_topic"),
                "camera_info_topic": LaunchConfiguration("camera_info_topic"),
                "manifest_path": LaunchConfiguration("manifest_path"),
                "output_dir": LaunchConfiguration("output_dir"),
                "capture_hz": LaunchConfiguration("capture_hz"),
                "target_total_frames": LaunchConfiguration("target_total_frames"),
                "world": LaunchConfiguration("world"),
                "camera_pose_gz_topic": LaunchConfiguration("camera_pose_gz_topic"),
                "camera_link_name": LaunchConfiguration("camera_link_name"),
            }
        ],
    )

    return LaunchDescription(
        [
            image_topic_arg,
            camera_info_topic_arg,
            gz_image_topic_arg,
            manifest_path_arg,
            output_dir_arg,
            capture_hz_arg,
            target_total_frames_arg,
            world_arg,
            camera_pose_topic_arg,
            camera_link_name_arg,
            bridge_launch,
            collector,
        ]
    )
