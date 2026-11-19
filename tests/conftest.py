import warnings

import pytest

warnings.filterwarnings("ignore", category=FutureWarning)

from pressready import samples  # noqa: E402


@pytest.fixture(scope="session")
def good_pdf(tmp_path_factory):
    return samples.make_good(tmp_path_factory.mktemp("pdf") / "good.pdf")


@pytest.fixture(scope="session")
def bad_pdf(tmp_path_factory):
    return samples.make_bad(tmp_path_factory.mktemp("pdf") / "bad.pdf")
