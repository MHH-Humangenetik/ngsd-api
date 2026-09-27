"""Tests for NgsdApi.get_parents_by_samples using mocked database responses."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ngsd_api import NgsdApi, NgsdSettings
from ngsd_api.types import Parents


@pytest.fixture
def api() -> NgsdApi:
    return NgsdApi(NgsdSettings(host="mock", user="mock", password="mock"))


def mock_session_with_responses(responses: list):
    """Create a mock session that returns the given responses in sequence."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=responses)

    @asynccontextmanager
    async def session_ctx():
        yield mock_session

    return session_ctx


@pytest.mark.asyncio
async def test_complete_partial_and_missing(api: NgsdApi) -> None:
    rows = [
        ("CHILD1", "FATHER1", "male"),
        ("CHILD1", "MOTHER1", "female"),
        ("CHILD2", "MOTHER2", "female"),
    ]
    responses = [MagicMock(fetchall=MagicMock(return_value=rows))]
    with patch.object(api, "session", mock_session_with_responses(responses)):
        parents = await api.get_parents_by_samples(
            ["CHILD1", "CHILD2", "ORPHAN", "CHILD1"]
        )
    assert parents == {
        "CHILD1": Parents(father="FATHER1", mother="MOTHER1"),
        "CHILD2": Parents(father=None, mother="MOTHER2"),
        "ORPHAN": Parents(father=None, mother=None),
    }


@pytest.mark.asyncio
async def test_empty_input_skips_query(api: NgsdApi) -> None:
    with patch.object(api, "session", mock_session_with_responses([])):
        assert await api.get_parents_by_samples([]) == {}
