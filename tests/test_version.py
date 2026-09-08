"""Guards the version string the release workflow checks against the git tag."""
import re

import viewer


def test_version_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", viewer.__version__), viewer.__version__


def test_version_has_no_v_prefix():
    # the workflow compares the tag with the "v" stripped, so the constant
    # must not carry one of its own
    assert not viewer.__version__.startswith("v")
