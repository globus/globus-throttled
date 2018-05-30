from setuptools import setup, find_packages

setup(
    name="globus_throttled",
    version=1.0,
    packages=find_packages(),
    install_requires=['tornado==5.0.2'],

    entry_points={
        'console_scripts': [
            'globus_throttled  = globus_throttled.daemon:run_daemon'
        ]
    },


    # descriptive info, non-critical
    description="Globus Throttler Daemon",
    url="https://github.com/globus/globus-throttled",
)
