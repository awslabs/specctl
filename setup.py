from setuptools import setup
from setuptools import find_packages

setup(
    name='specctl',
    version='0.1.0',
    py_modules=['specctl'],
    install_requires=[
        'Click',
        'PyYAML',
        'kubernetes',
        'boto3',
        'botocore',
        'pick'
    ],
    entry_points={
        'console_scripts': [
            'specctl = specctl.specctl:transform',
        ],
    },
)
