"""
Setup script for xYang library.
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="xyang",
    version="0.1.1",
    author="Exergy LLC",
    description="A Python library implementing a subset of YANG features focused on constraint validation",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/exergy-connect/xYang",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Networking",
    ],
    python_requires=">=3.9",
    install_requires=[],  # No dependencies - pure Python; dev deps live in pyproject.toml
)
