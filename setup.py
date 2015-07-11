from setuptools import setup, find_packages

setup(
    name='mybuild-embox',
    version='0.1',

    description='Build tools for Embox',
    url='https://github.com/vloginova/mybuild-embox',

    author='Vita Loginova',
    author_email='vita.loginova@gmail.com',

    license='BSD',

    classifiers=[
        'Private :: Do Not Upload',

        'Development Status :: 3 - Alpha',

        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',

        'License :: OSI Approved :: BSD License',

        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],
    keywords='mybuild build automation development tools',

    packages=find_packages(),

    install_requires=['ply>=3.6'],
)
