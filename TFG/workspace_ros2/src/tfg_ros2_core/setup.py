from glob import glob
import os
from setuptools import find_packages, setup

package_name = 'tfg_ros2_core'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob(os.path.join('launch', '*.launch.py'))),
        (os.path.join('share', package_name, 'config'),
            glob(os.path.join('config', '*.yaml'))),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Javier Martínez López',
    maintainer_email='GustaveLumiere@proton.me',  # Tomado de git log / git config; sustituible
    description='Paquete base ROS 2 Humble para orquestación, tiempo de simulación y teleoperación del TFG.',
    license='MIT',  # Provisional: no existe archivo LICENSE en el repositorio
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
        ],
    },
)