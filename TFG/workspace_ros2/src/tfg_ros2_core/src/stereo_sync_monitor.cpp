#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include <string>

#include <message_filters/subscriber.h>
#include <message_filters/sync_policies/approximate_time.h>
#include <message_filters/synchronizer.h>
#include <rclcpp/rclcpp.hpp>
#include <rmw/qos_profiles.h>
#include <sensor_msgs/msg/camera_info.hpp>
#include <sensor_msgs/msg/image.hpp>

namespace
{

constexpr std::uint32_t kExpectedWidth = 1280U;
constexpr std::uint32_t kExpectedHeight = 720U;
constexpr double kMinFxEpsilon = 1e-6;
constexpr double kMinValidBaselineM = 0.01;
constexpr double kMaxValidBaselineM = 0.50;
constexpr double kTargetMinBaselineM = 0.06;
constexpr double kTargetMaxBaselineM = 0.10;
constexpr double kBoundaryEps = 1e-6;

}  // namespace

/**
 * @brief Nodo monitor para verificar sincronización, resolución y baseline del par estéreo.
 */
class StereoSyncMonitor : public rclcpp::Node
{
public:
  StereoSyncMonitor()
  : Node("stereo_sync_monitor")
  {
    const int raw_queue_size = this->declare_parameter<int>("sync_queue_size", 20);
    int queue_size = raw_queue_size;
    if (queue_size < 1) {
      RCLCPP_WARN(
        this->get_logger(),
        "sync_queue_size (%d) debe ser >= 1; se ajusta al mínimo seguro 1.",
        raw_queue_size);
      queue_size = 1;
    }

    // Best-effort en el suscriptor es compatible con publicadores Reliable y BestEffort.
    rmw_qos_profile_t camera_qos = rmw_qos_profile_sensor_data;
    camera_qos.depth = static_cast<std::size_t>(queue_size);

    left_img_sub_.subscribe(this, "/camera/left/image_raw", camera_qos);
    right_img_sub_.subscribe(this, "/camera/right/image_raw", camera_qos);
    left_info_sub_.subscribe(this, "/camera/left/camera_info", camera_qos);
    right_info_sub_.subscribe(this, "/camera/right/camera_info", camera_qos);

    sync_ = std::make_shared<Synchronizer>(
      SyncPolicy(static_cast<std::uint32_t>(queue_size)),
      left_img_sub_,
      right_img_sub_,
      left_info_sub_,
      right_info_sub_);

    sync_->registerCallback(
      std::bind(
        &StereoSyncMonitor::onSyncedStereo,
        this,
        std::placeholders::_1,
        std::placeholders::_2,
        std::placeholders::_3,
        std::placeholders::_4));

    last_ros_time_ = this->now();
    last_wall_time_ = std::chrono::steady_clock::now();

    // Wall timer para seguir informando aunque /clock o las cámaras estén detenidos.
    report_timer_ = this->create_wall_timer(
      std::chrono::seconds(2),
      std::bind(&StereoSyncMonitor::onReportTimer, this));

    bool use_sim_time = false;
    if (this->has_parameter("use_sim_time")) {
      use_sim_time = this->get_parameter("use_sim_time").as_bool();
    }

    RCLCPP_INFO(
      this->get_logger(),
      "stereo_sync_monitor iniciado (sync_queue_size=%d, use_sim_time=%s).",
      queue_size,
      use_sim_time ? "true" : "false");
  }

private:
  using SyncPolicy = message_filters::sync_policies::ApproximateTime<
    sensor_msgs::msg::Image,
    sensor_msgs::msg::Image,
    sensor_msgs::msg::CameraInfo,
    sensor_msgs::msg::CameraInfo>;
  using Synchronizer = message_filters::Synchronizer<SyncPolicy>;

  struct WindowStats
  {
    std::size_t pair_count{0U};
    double max_skew_ms{0.0};
    bool any_resolution_mismatch{false};
    std::uint32_t left_img_w{0U};
    std::uint32_t left_img_h{0U};
    std::uint32_t right_img_w{0U};
    std::uint32_t right_img_h{0U};
    std::uint32_t left_info_w{0U};
    std::uint32_t left_info_h{0U};
    std::uint32_t right_info_w{0U};
    std::uint32_t right_info_h{0U};
    double right_p0{0.0};
    double right_p3{0.0};
  };

  void onSyncedStereo(
    const sensor_msgs::msg::Image::ConstSharedPtr & left_img,
    const sensor_msgs::msg::Image::ConstSharedPtr & right_img,
    const sensor_msgs::msg::CameraInfo::ConstSharedPtr & left_info,
    const sensor_msgs::msg::CameraInfo::ConstSharedPtr & right_info)
  {
    const std::int64_t left_ns =
      static_cast<std::int64_t>(left_img->header.stamp.sec) * 1000000000LL +
      static_cast<std::int64_t>(left_img->header.stamp.nanosec);
    const std::int64_t right_ns =
      static_cast<std::int64_t>(right_img->header.stamp.sec) * 1000000000LL +
      static_cast<std::int64_t>(right_img->header.stamp.nanosec);
    const std::int64_t diff_ns =
      (left_ns >= right_ns) ? (left_ns - right_ns) : (right_ns - left_ns);
    const double skew_ms = static_cast<double>(diff_ns) / 1e6;

    const bool res_mismatch =
      (left_img->width != kExpectedWidth || left_img->height != kExpectedHeight ||
      right_img->width != kExpectedWidth || right_img->height != kExpectedHeight ||
      left_info->width != kExpectedWidth || left_info->height != kExpectedHeight ||
      right_info->width != kExpectedWidth || right_info->height != kExpectedHeight);

    std::lock_guard<std::mutex> lock(stats_mutex_);
    ++window_.pair_count;
    window_.max_skew_ms = std::max(window_.max_skew_ms, skew_ms);
    window_.any_resolution_mismatch = window_.any_resolution_mismatch || res_mismatch;

    window_.left_img_w = left_img->width;
    window_.left_img_h = left_img->height;
    window_.right_img_w = right_img->width;
    window_.right_img_h = right_img->height;
    window_.left_info_w = left_info->width;
    window_.left_info_h = left_info->height;
    window_.right_info_w = right_info->width;
    window_.right_info_h = right_info->height;
    window_.right_p0 = right_info->p[0];
    window_.right_p3 = right_info->p[3];
  }

  void onReportTimer()
  {
    const rclcpp::Time now_ros = this->now();
    const auto now_wall = std::chrono::steady_clock::now();

    WindowStats snapshot;
    rclcpp::Time prev_ros;
    std::chrono::steady_clock::time_point prev_wall;
    {
      std::lock_guard<std::mutex> lock(stats_mutex_);
      snapshot = window_;
      window_ = WindowStats{};
      prev_ros = last_ros_time_;
      prev_wall = last_wall_time_;
      last_ros_time_ = now_ros;
      last_wall_time_ = now_wall;
    }

    const double dt_wall =
      std::chrono::duration<double>(now_wall - prev_wall).count();

    // Evita dividir por un salto inicial 0 -> sim_time o retrocesos de /clock.
    double dt_ros = 0.0;
    if (prev_ros.nanoseconds() > 0 &&
      now_ros.nanoseconds() > 0 &&
      now_ros.get_clock_type() == prev_ros.get_clock_type())
    {
      dt_ros = (now_ros - prev_ros).seconds();
    }

    const bool using_ros_clock = (dt_ros > 0.0);
    const double dt = using_ros_clock ? dt_ros : dt_wall;

    if (snapshot.pair_count == 0U) {
      RCLCPP_INFO(
        this->get_logger(),
        "Pares estéreo sincronizados: 0.00 Hz (esperando pares estéreo sincronizados y /clock)");
      return;
    }

    const double safe_dt = (dt > 1e-6) ? dt : 2.0;
    const double freq_hz = static_cast<double>(snapshot.pair_count) / safe_dt;
    const char * clock_label = using_ros_clock ? "ROS" : "wall";

    const double p0 = snapshot.right_p0;
    const double p3 = snapshot.right_p3;
    const bool p0_invalid =
      (!std::isfinite(p0) || !std::isfinite(p3) || std::abs(p0) < kMinFxEpsilon);

    if (p0_invalid) {
      RCLCPP_INFO(
        this->get_logger(),
        "Sync estéreo: %.2f Hz (%s, %zu pares) | Res L: %ux%u R: %ux%u | Desfase máx: %.3f ms | Baseline: N/A (P[0] inválido)",
        freq_hz,
        clock_label,
        snapshot.pair_count,
        snapshot.left_img_w,
        snapshot.left_img_h,
        snapshot.right_img_w,
        snapshot.right_img_h,
        snapshot.max_skew_ms);

      RCLCPP_WARN(
        this->get_logger(),
        "No se puede calcular el baseline estéreo: right_info->p[0]=%.6e (< 1e-6 o no finito; p[3]=%.6e).",
        p0,
        p3);
    } else {
      const double baseline_m = -p3 / p0;

      RCLCPP_INFO(
        this->get_logger(),
        "Sync estéreo: %.2f Hz (%s, %zu pares) | Res L: %ux%u R: %ux%u | Desfase máx: %.3f ms | Baseline: %.4f m",
        freq_hz,
        clock_label,
        snapshot.pair_count,
        snapshot.left_img_w,
        snapshot.left_img_h,
        snapshot.right_img_w,
        snapshot.right_img_h,
        snapshot.max_skew_ms,
        baseline_m);

      if (!std::isfinite(baseline_m)) {
        RCLCPP_WARN(
          this->get_logger(),
          "Baseline estéreo no finito obtenido desde right_info->p[0]=%.6f, p[3]=%.6f.",
          p0,
          p3);
      } else if (baseline_m <= 0.0) {
        RCLCPP_WARN(
          this->get_logger(),
          "Baseline estéreo <= 0.0 m (%.4f m; p[0]=%.3f, p[3]=%.3f). Revisa el signo de Tx en right_info->p[3].",
          baseline_m,
          p0,
          p3);
      } else if (baseline_m < (kMinValidBaselineM - kBoundaryEps) ||
        baseline_m > (kMaxValidBaselineM + kBoundaryEps))
      {
        RCLCPP_WARN(
          this->get_logger(),
          "Baseline estéreo incoherente: %.4f m está fuera del rango válido [0.01, 0.50] m.",
          baseline_m);
      } else if (baseline_m < (kTargetMinBaselineM - kBoundaryEps) ||
        baseline_m > (kTargetMaxBaselineM + kBoundaryEps))
      {
        RCLCPP_WARN(
          this->get_logger(),
          "Baseline estéreo (%.4f m) fuera del rango objetivo TurtleBot3 [0.06, 0.10] m.",
          baseline_m);
      }
    }

    if (snapshot.any_resolution_mismatch) {
      RCLCPP_WARN(
        this->get_logger(),
        "Resolución distinta de 1280x720 detectada (Img L: %ux%u, Img R: %ux%u, Info L: %ux%u, Info R: %ux%u).",
        snapshot.left_img_w,
        snapshot.left_img_h,
        snapshot.right_img_w,
        snapshot.right_img_h,
        snapshot.left_info_w,
        snapshot.left_info_h,
        snapshot.right_info_w,
        snapshot.right_info_h);
    }
  }

  message_filters::Subscriber<sensor_msgs::msg::Image> left_img_sub_;
  message_filters::Subscriber<sensor_msgs::msg::Image> right_img_sub_;
  message_filters::Subscriber<sensor_msgs::msg::CameraInfo> left_info_sub_;
  message_filters::Subscriber<sensor_msgs::msg::CameraInfo> right_info_sub_;
  std::shared_ptr<Synchronizer> sync_;
  rclcpp::TimerBase::SharedPtr report_timer_;

  std::mutex stats_mutex_;
  WindowStats window_;
  rclcpp::Time last_ros_time_;
  std::chrono::steady_clock::time_point last_wall_time_;
};

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<StereoSyncMonitor>();
  rclcpp::spin(node);
  node.reset();
  rclcpp::shutdown();
  return 0;
}
