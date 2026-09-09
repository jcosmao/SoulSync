"""Album Pre-flight scores a candidate folder on what the search returned, then
downloads everything the browse returns. These cover the check that compares
the two before committing to the folder.
"""

import pytest

from core.downloads.master import (
    _MAX_RELEASE_FOLDER_TRACKS,
    _folder_is_plausible_release,
)


@pytest.mark.parametrize("folder,expected,matched", [
    (12, 12, 12),          # exactly the release
    (13, 12, 6),           # a bonus track
    (24, 12, 5),           # two discs under one folder
    (36, 12, 5),           # three discs — 3x expected is still allowed
    (11, 0, 11),           # no metadata: what the search matched is the yardstick
    (14, 0, 5),            # no metadata, slack of +10 on the matched count
    (1, 1, 1),             # a single
])
def test_a_real_release_is_accepted(folder, expected, matched):
    assert _folder_is_plausible_release(folder, expected, matched)


@pytest.mark.parametrize("folder,expected,matched", [
    (36377, 12, 5),        # the case this exists for: a peer's whole share
    (627, 12, 4),          # a genre dump the search matched a few tracks in
    (40, 12, 5),           # past 3x and past +10
    (100, 0, 5),           # no metadata, and far past what was matched
])
def test_a_folder_that_is_not_one_release_is_refused(folder, expected, matched):
    assert not _folder_is_plausible_release(folder, expected, matched)


def test_the_ceiling_holds_even_for_a_large_release():
    """A box set is still not 300+ files, whatever the metadata claims."""
    assert not _folder_is_plausible_release(_MAX_RELEASE_FOLDER_TRACKS + 1, 200, 200)
    assert _folder_is_plausible_release(_MAX_RELEASE_FOLDER_TRACKS, 200, 200)


def test_metadata_wins_over_what_the_search_matched():
    """The search matching five tracks does not make a 30-track folder wrong
    when the release has 30 tracks."""
    assert _folder_is_plausible_release(30, 30, 5)
    # ...and without the metadata, five matched tracks make 30 implausible.
    assert not _folder_is_plausible_release(30, 0, 5)


def test_an_empty_browse_is_left_to_the_caller():
    assert _folder_is_plausible_release(0, 12, 5)
