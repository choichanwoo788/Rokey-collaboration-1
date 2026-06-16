from setuptools import find_packages, setup

package_name = 'cobot1_project'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='ccw',
    maintainer_email='ccw@todo.todo',
    description='TODO: Package description',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'app = cobot1_project.app:main',
            'app2_1_ch = cobot1_project.app2_1_ch:main',
            'pepper_salt_pick2_7 = cobot1_project.pepper_salt_pick2_7:main',
            'pepper_salt_pick2_9_ch = cobot1_project.pepper_salt_pick2_9_ch:main',
            'pepper_salt_pick2_10_ch = cobot1_project.pepper_salt_pick2_10_ch:main',
            'source3_4 = cobot1_project.source3_4:main',
            'source3_5_ch = cobot1_project.source3_5_ch:main',
            'central_controller1_1_ch = cobot1_project.central_controller1_1_ch:main',
            'central_controller1_2_cho = cobot1_project.central_controller1_2_cho:main',
           'fryflip_2_3 = cobot1_project.fryflip_2_3:main',
            'fryflip_2_4_ch = cobot1_project.fryflip_2_4_ch:main',
            'move_tenderizing_service3_3_2 = cobot1_project.move_tenderizing_service3_3_2:main',
            'move_tenderizing_service3_3_3_ch = cobot1_project.move_tenderizing_service3_3_3_ch:main',
            'recovery1_1_ch = cobot1_project.recovery1_1_ch:main',
            'seasoning_service_server_1_1_ch = cobot1_project.seasoning_service_server_1_1_ch:main',
            'all_task_service_server = cobot1_project.all_task_service_server:main',
            'all_task_service_server_1_cho = cobot1_project.all_task_service_server_1_cho:main',
            'seasoning_task_once = cobot1_project.seasoning_task_once:main',
            'seasoning_task_once_back = cobot1_project.seasoning_task_once_back:main',
            'tenderizing_task_once = cobot1_project.tenderizing_task_once:main',
            'frying_task_once = cobot1_project.frying_task_once:main',
            'saucing_task_once = cobot1_project.saucing_task_once:main',
            'recovery_task_once = cobot1_project.recovery_task_once:main',
            'all_task_service_server_2 = cobot1_project.all_task_service_server_2:main',
            'central_controller1_3 = cobot1_project.central_controller1_3:main',
            'recovery_task_once_3 = cobot1_project.recovery_task_once_3:main',
        ],
    },
)
