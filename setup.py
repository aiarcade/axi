from setuptools import setup

setup(
    name='axi',
    version='0.1',
    description='Library for working with the AxiDraw v3 pen plotter.',
    author='Michael Fogleman',
    author_email='michael.fogleman@gmail.com',
    packages=['axi'],
    install_requires=['pyserial', 'shapely', 'pyhull', 'cairocffi'],
    entry_points={
        'console_scripts': [
            'axi = axi.main:main'
        ]
    },
    license='MIT',
    python_requires='>=3',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: Implementation :: CPython',
    ],
)
