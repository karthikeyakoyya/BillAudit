import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from billaudit.config import Config  # noqa: E402
from billaudit.generate import generate  # noqa: E402
from billaudit.harness import run_on_dataset  # noqa: E402

CFG = replace(Config(), seed=7, n_circuits=200)


@pytest.fixture(scope="session")
def cfg():
    return CFG


@pytest.fixture(scope="session")
def data_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("data")
    generate(CFG, d)
    return d


@pytest.fixture(scope="session")
def scored(data_dir):
    findings, truth, dq, raw = run_on_dataset(CFG, data_dir)
    return {"findings": findings, "truth": truth, "dq": dq, "raw": raw, "data_dir": data_dir}
