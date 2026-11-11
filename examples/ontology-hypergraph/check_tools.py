#!/usr/bin/env python3
"""Independent YANG syntax and effective data validation; no xYang schema adapter."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from collector import HERE


def check(tree):
    from yangson.datamodel import DataModel

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pyang",
            "--lint",
            "-p",
            str(HERE / "models"),
            *map(str, sorted((HERE / "models").glob("*.yang"))),
        ],
        check=True,
    )
    model = DataModel.from_file(str(HERE / "yangson-library.json"), [str(HERE / "models")])
    model.from_raw(tree).validate()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("projection", type=Path)
    args = parser.parse_args()
    check(json.loads(args.projection.read_text()))
    print("pyang syntax and Yangson effective-tree validation passed")
