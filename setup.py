from setuptools import setup, find_packages

setup(
    name="opencv-screen-capture",
    version="0.1.0",
    description="Screen capture utility using OpenCV and MSS",
    author="Your Name",
    author_email="your.email@example.com",
    url="https://github.com/yourusername/opencv-screen-capture",
    packages=find_packages(),
    install_requires=[
        "opencv-python>=4.5.0",
        "numpy>=1.19.0",
        "mss>=6.1.0",
        "pillow>=8.0.0",
    ],
    entry_points={
        "console_scripts": [
            "screen-capture=src.main:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
    python_requires=">=3.7",
)