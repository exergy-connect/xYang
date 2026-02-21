"""
Setup script for xYang library.
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="xYang",
    version="0.1.0",
    author="Exergy LLC",
    description="A Python library implementing a subset of YANG features focused on constraint validation",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/exergy-connect/xYang",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Networking",
    ],
    python_requires=">=3.8",
    install_requires=[],  # No dependencies - pure Python
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "black>=23.0.0",
        ],
    },
)
