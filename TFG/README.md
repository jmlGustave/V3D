# TFG: Evaluación y Benchmarking de Algoritmos SLAM Visual y Navegación Autónoma mediante Simulación Fotorrealista en NVIDIA Isaac Sim y ROS 2

**Autor:** Javier Martínez López  
**Titulación:** Grado en Ingeniería Robótica e Informática Industrial (UPV)  
**Esquema de Arquitectura:** [Ver Diagrama UML en `Arquitectura.md`](./Arquitectura.md)

---

## 1. Descripción del Proyecto

Este proyecto desarrolla un entorno de simulación modular de alta fidelidad (Gemelo Digital) para evaluar, comparar y validar arquitecturas de **SLAM Visual (Simultaneous Localization and Mapping)** y navegación autónoma bajo condiciones fotorrealistas con trazado de rayos (*Ray Tracing*).

La arquitectura desacopla el motor de físicas y renderizado (**NVIDIA Isaac Sim 6.2**) del stack de percepción y control (**ROS 2**) mediante contenedores Docker aislados que comparten la pila de red del sistema anfitrión (`network_mode: "host"`), garantizando una comunicación DDS de baja latencia sin sobrecarga de virtualización de red.

---

## 2. Explicación Detallada de la Arquitectura

El sistema (representado gráficamente en [`Arquitectura.md`](./Arquitectura.md)) se estructura en cinco bloques funcionales interconectados:

### 2.1. Capa de Hardware y Asignación de Recursos
* **GPU (NVIDIA GeForce RTX 5060 Ti - 16 GB VRAM):** Asume una doble carga computacional concurrente: ejecuta el motor de renderizado con trazado de rayos en tiempo real (**RTX Real-Time 2.0**) en Omniverse y acelera mediante **TensorRT** la inferencia del pipeline de odometría visual neuronal (**Isaac cuVSLAM**).
* **CPU (Intel Core Ultra):** Ejecuta en paralelo la extracción clásica de características ORB y optimización de grafos (**ORB-SLAM3**), el filtrado espacial de nubes de puntos (**PCL**) y los planificadores de trayectorias de **Nav2**.
* **Almacenamiento NVMe:** Garantiza la carga rápida de escenas complejas y activos `.usd` sin cuellos de botella de lectura/escritura.

### 2.2. Contenedor 1: Simulación Física y Sensorial (`tfg_isaac_sim`)
* **Omniverse Kit & Gemelo Digital (USD):** Simula las físicas del entorno industrial (PhysX) y de la plataforma robótica, generando datos sintéticos de sensores con iluminación y materiales físicamente precisos.
* **OmniGraph Pipeline & ROS 2 Bridge:** Captura los *frames* del par estéreo, la odometría de ruedas y el árbol cinemático del robot en cada paso de simulación y los expone directamente al bus DDS de ROS 2.

### 2.3. Bus de Comunicaciones DDS (Tópicos ROS 2)
* **`/camera` (`left`, `right`, `camera_info`):** Flujo de imágenes estéreo rectificadas y matrices de calibración intrínseca/extrínseca.
* **`/odom` y `/tf` (`/tf_static`):** Estimación odométrica base y árbol de transformaciones espaciales entre los eslabones del robot y el mundo.
* **`/map` y `/cmd_vel`:** Mapa de ocupación generado para navegación y cierre del lazo de control mediante consignas de velocidad lineal y angular $(v, \omega)$.

### 2.4. Contenedor 2: Procesamiento, Percepción y Control (`tfg_ros2_core`)
* **Sincronización y Preprocesamiento (`message_filters` + `PCL VoxelGrid`):** Asegura la correspondencia temporal exacta entre el par de cámaras (`TimeSync`) y aplica un diezmado espacial mediante rejilla de vóxeles (*VoxelGrid*) para reducir la densidad computacional y exportar representaciones en 2D (`.pcd`), 3D volumétrico OctoMap (`.bt`) y nube de puntos 3D (`.pcd`).
* **Evaluación Dual de SLAM:**
  * **Enfoque Clásico (`ORB-SLAM3`):** Basado en descriptores geométricos ORB, seguimiento de *keyframes* y *Bundle Adjustment* sobre CPU.
  * **Enfoque Neuronal / Acelerado (`Isaac cuVSLAM`):** Odometría visual y SLAM acelerado por hardware en GPU para evaluar su robustez frente a cambios de iluminación y superficies con baja textura.
* **Navegación Autónoma (`Nav2 Stack`):** Consume la pose 3D estimada por el módulo SLAM activo y el mapa del entorno para calcular trayectorias libres de colisiones y enviar comandos `/cmd_vel` de vuelta al gemelo digital en Isaac Sim.

### 2.5. Herramientas de Telemetría y Benchmarking
* **`rqt_reconfigure`:** Ajuste en caliente (*Real-Time*) de hiperparámetros del filtro VoxelGrid y costes de navegación sin reiniciar nodos.
* **`RViz2`:** Monitorización visual del árbol `/tf`, nubes de puntos filtradas y mapas de coste.
* **`evo`:** Herramienta de evaluación matemática que compara las trayectorias estimadas por `ORB-SLAM3` y `cuVSLAM` frente al *Ground Truth* exacto del simulador mediante métricas **APE** (*Absolute Pose Error*) y **RPE** (*Relative Pose Error*).

---

## 3. Validación y Pruebas de Rendimiento Iniciales (Benchmarking de Hardware)

Se ha validado el despliegue de la arquitectura de contenedores sobre **Arch Linux (Kernel 7.1.9 / Hyprland)** ejecutando **Isaac Sim 6.2.0** con aceleración por hardware Vulkan y renderizado **RTX - Real-Time 2.0**:

| Métrica | Resultado Obtenido | Observaciones |
| :--- | :--- | :--- |
| **GPU Activa** | NVIDIA GeForce RTX 5060 Ti (16 GB) | Drivers `615.78.08` (API Vulkan nativa en contenedor) |
| **Tasa de Fotogramas (FPS)** | **110.13 FPS** | Simulación fluida por encima del umbral de tiempo real (60 Hz) |
| **Tiempo de Frame (Frame Time)** | **8.20 ms** | Baja latencia de renderizado a resolución `1280x720` |
| **Uso de VRAM (GPU)** | **888.8 MiB usados** (13.2 GiB disponibles) | Más del 80% de VRAM libre para carga de almacén e inferencia `cuVSLAM` |
| **Uso de RAM (Sistema)** | **8.2 GiB usados** (50.8 GiB disponibles) | Margen holgado sobre los 64 GB DDR5 del sistema para el contenedor ROS 2 |

---

## 4. Instrucciones de Despliegue Rápido

```bash
# 1. Autorizar conexiones gráficas locales al servidor Xwayland
xhost +local:

# 2. Levantar los contenedores de simulación y ROS 2 en segundo plano
docker-compose up -d

# 3. Acceder al contenedor de Isaac Sim y lanzar la interfaz gráfica
docker exec -it tfg_isaac_sim bash
cd /isaac-sim
./isaac-sim.sh --/app/window/enabled=true --/app/window/hideUi=false --/app/window/width=1280 --/app/window/height=720