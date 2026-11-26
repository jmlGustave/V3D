cmake_minimum_required(VERSION 3.8)
project(tfg_ros2_core)

# Compilación estricta en C++17
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(message_filters REQUIRED)

add_executable(stereo_sync_monitor
  src/stereo_sync_monitor.cpp
)
ament_target_dependencies(stereo_sync_monitor
  rclcpp
  sensor_msgs
  message_filters
)

add_executable(tum_trajectory_logger
  src/tum_trajectory_logger.cpp
)
ament_target_dependencies(tum_trajectory_logger
  rclcpp
  nav_msgs
  geometry_msgs
)

install(TARGETS
  stereo_sync_monitor
  tum_trajectory_logger
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY
  launch
  config
  DESTINATION share/${PROJECT_NAME}
)

install(DIRECTORY
  scripts
  DESTINATION share/${PROJECT_NAME}
  USE_SOURCE_PERMISSIONS
)

ament_package()
