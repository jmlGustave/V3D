#include <cstddef>
#include <exception>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iomanip>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <system_error>

#include <nav_msgs/msg/odometry.hpp>
#include <rclcpp/rclcpp.hpp>

namespace
{

constexpr std::size_t kFlushEveryNMessages = 30U;

}  // namespace

/**
 * @brief Nodo registrador de trayectorias nav_msgs/msg/Odometry en formato TUM.
 */
class TumTrajectoryLogger : public rclcpp::Node
{
public:
  TumTrajectoryLogger()
  : Node("tum_trajectory_logger")
  {
    odom_topic_ = this->declare_parameter<std::string>("odom_topic", "/ground_truth/odom");
    output_file_ = this->declare_parameter<std::string>("output_file", "trajectory_gt.tum");

    if (odom_topic_.empty()) {
      RCLCPP_ERROR(this->get_logger(), "El parámetro 'odom_topic' no puede estar vacío.");
      throw std::invalid_argument("odom_topic vacío");
    }
    if (output_file_.empty()) {
      RCLCPP_ERROR(this->get_logger(), "El parámetro 'output_file' no puede estar vacío.");
      throw std::invalid_argument("output_file vacío");
    }

    const std::filesystem::path output_path(output_file_);
    const std::filesystem::path parent_dir = output_path.parent_path();
    if (!parent_dir.empty()) {
      std::error_code ec;
      std::filesystem::create_directories(parent_dir, ec);
      if (ec) {
        RCLCPP_ERROR(
          this->get_logger(),
          "No se pudo crear el directorio padre '%s': %s",
          parent_dir.string().c_str(),
          ec.message().c_str());
        throw std::runtime_error("Fallo creando el directorio padre de output_file");
      }
    }

    output_stream_.open(output_path, std::ios::out | std::ios::trunc);
    if (!output_stream_.is_open()) {
      RCLCPP_ERROR(
        this->get_logger(),
        "No se pudo abrir el archivo TUM '%s' para escritura.",
        output_file_.c_str());
      throw std::runtime_error("Fallo abriendo output_file");
    }

    output_stream_ << "# timestamp tx ty tz qx qy qz qw\n";
    output_stream_.flush();
    if (!output_stream_.good()) {
      RCLCPP_ERROR(
        this->get_logger(),
        "Error escribiendo la cabecera TUM en '%s'.",
        output_file_.c_str());
      throw std::runtime_error("Fallo escribiendo cabecera TUM");
    }

    odom_sub_ = this->create_subscription<nav_msgs::msg::Odometry>(
      odom_topic_,
      rclcpp::QoS(rclcpp::KeepLast(100)),
      std::bind(&TumTrajectoryLogger::onOdometry, this, std::placeholders::_1));

    bool use_sim_time = false;
    if (this->has_parameter("use_sim_time")) {
      use_sim_time = this->get_parameter("use_sim_time").as_bool();
    }

    RCLCPP_INFO(
      this->get_logger(),
      "tum_trajectory_logger iniciado (odom_topic='%s', output_file='%s', use_sim_time=%s).",
      odom_topic_.c_str(),
      output_file_.c_str(),
      use_sim_time ? "true" : "false");
  }

  ~TumTrajectoryLogger() override
  {
    std::size_t total_poses = 0U;
    {
      std::lock_guard<std::mutex> lock(file_mutex_);
      if (output_stream_.is_open()) {
        output_stream_.flush();
        output_stream_.close();
      }
      total_poses = pose_count_;
    }

    RCLCPP_INFO(
      this->get_logger(),
      "Trayectoria TUM cerrada en '%s'. Total de poses guardadas: %zu",
      output_file_.c_str(),
      total_poses);
  }

private:
  void onOdometry(const nav_msgs::msg::Odometry::ConstSharedPtr & msg)
  {
    const auto & pos = msg->pose.pose.position;
    const auto & ori = msg->pose.pose.orientation;

    std::lock_guard<std::mutex> lock(file_mutex_);
    if (!output_stream_.is_open()) {
      return;
    }

    // Construimos sec.nanosec directamente para preservar precisión exacta del timestamp.
    output_stream_ << msg->header.stamp.sec << '.'
                   << std::setw(9) << std::setfill('0') << msg->header.stamp.nanosec
                   << std::setfill(' ')
                   << ' ' << std::fixed << std::setprecision(9)
                   << pos.x << ' ' << pos.y << ' ' << pos.z
                   << ' ' << ori.x << ' ' << ori.y << ' ' << ori.z << ' ' << ori.w
                   << '\n';

    ++pose_count_;
    if (pose_count_ % kFlushEveryNMessages == 0U) {
      output_stream_.flush();
    }
  }

  std::string odom_topic_;
  std::string output_file_;
  std::mutex file_mutex_;
  std::ofstream output_stream_;
  std::size_t pose_count_{0U};
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odom_sub_;
};

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  try {
    auto node = std::make_shared<TumTrajectoryLogger>();
    rclcpp::spin(node);
    node.reset();
  } catch (const std::exception & ex) {
    RCLCPP_FATAL(
      rclcpp::get_logger("tum_trajectory_logger"),
      "Error inicializando tum_trajectory_logger: %s",
      ex.what());
    rclcpp::shutdown();
    return 1;
  }
  rclcpp::shutdown();
  return 0;
}
