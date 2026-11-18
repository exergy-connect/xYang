"""Include the repository's shared YANG modules in the Python distribution."""
from pathlib import Path
from shutil import copy2

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildWithSharedYang(build_py):
    def run(self):
        super().run()
        destination = Path(self.build_lib) / "xyang" / "shared"
        destination.mkdir(parents=True, exist_ok=True)
        for source in Path("shared").glob("*.yang"):
            copy2(source, destination / source.name)


setup(cmdclass={"build_py": BuildWithSharedYang})
