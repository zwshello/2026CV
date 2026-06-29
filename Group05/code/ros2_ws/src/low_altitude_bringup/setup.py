from setuptools import find_packages, setup


package_name = "low_altitude_bringup"


setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (
            f"share/{package_name}/launch",
            [
                "launch/sim_bridge.launch.py",
                "launch/perception_yolo.launch.py",
                "launch/dataset_collect.launch.py",
            ],
        ),
        (
            f"share/{package_name}/config",
            [
                "config/gz_bridge_clock.yaml",
            ],
        ),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="2026CV Team",
    maintainer_email="student@example.com",
    description="ROS 2 bringup utilities for the 2026CV low-altitude PX4 and Gazebo project.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "gz_camera_bridge = low_altitude_bringup.gz_camera_bridge:main",
            "image_snapshot = low_altitude_bringup.image_snapshot:main",
            "image_throttle = low_altitude_bringup.image_throttle:main",
            "yolo_detector = low_altitude_bringup.yolo_detector:main",
            "dataset_collector = low_altitude_bringup.dataset_collector:main",
        ],
    },
)
