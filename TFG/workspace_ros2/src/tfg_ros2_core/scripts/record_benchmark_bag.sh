#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    echo "Uso: $0 [directorio_base]"
    echo "  Graba un rosbag2 reproducible con los 8 tópicos de referencia (default: bags)."
    exit 0
fi

if ! command -v ros2 >/dev/null 2>&1; then
    echo "Error: 'ros2' no está en PATH. Ejecuta 'source /opt/ros/humble/setup.bash'." >&2
    exit 1
fi

BAG_DIR="${1:-bags}"
mkdir -p "${BAG_DIR}"

OUTPUT_PATH="${BAG_DIR%/}/tfg_run_$(date +%Y%m%d_%H%M%S)"
echo "Grabando rosbag2 en: ${OUTPUT_PATH}"

exec ros2 bag record \
    -o "${OUTPUT_PATH}" \
    /clock \
    /camera/left/image_raw \
    /camera/left/camera_info \
    /camera/right/image_raw \
    /camera/right/camera_info \
    /tf \
    /tf_static \
    /ground_truth/odom
