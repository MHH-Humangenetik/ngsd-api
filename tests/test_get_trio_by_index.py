"""Tests for NgsdApi.get_trio_by_index using mocked database responses."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ngsd_api import NgsdApi, NgsdSettings
from ngsd_api.types import Trio


@pytest.fixture
def api() -> NgsdApi:
    return NgsdApi(NgsdSettings(host="mock", password="mock"))


def mock_session_with_responses(responses: list):
    """Create a mock session that returns the given responses in sequence."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=responses)

    @asynccontextmanager
    async def session_ctx():
        yield mock_session

    return session_ctx


@pytest.mark.asyncio
async def test_complete_trio(api: NgsdApi) -> None:
    responses = [
        MagicMock(fetchone=MagicMock(return_value=(123,))),
        MagicMock(fetchall=MagicMock(return_value=[("FATHER", "male"), ("MOTHER", "female")])),
    ]
    with patch.object(api, "session", mock_session_with_responses(responses)):
        trio = await api.get_trio_by_index("CHILD")
    assert trio == Trio(child="CHILD", father="FATHER", mother="MOTHER")


@pytest.mark.asyncio
async def test_no_sample(api: NgsdApi) -> None:
    responses = [MagicMock(fetchone=MagicMock(return_value=None))]
    with patch.object(api, "session", mock_session_with_responses(responses)):
        with pytest.raises(ValueError, match="no sample named 'UNKNOWN'"):
            await api.get_trio_by_index("UNKNOWN")


@pytest.mark.asyncio
async def test_no_parents(api: NgsdApi) -> None:
    responses = [
        MagicMock(fetchone=MagicMock(return_value=(123,))),
        MagicMock(fetchall=MagicMock(return_value=[])),
    ]
    with patch.object(api, "session", mock_session_with_responses(responses)):
        with pytest.raises(ValueError, match="sample 'ORPHAN' has no parents"):
            await api.get_trio_by_index("ORPHAN")


@pytest.mark.asyncio
async def test_no_father(api: NgsdApi) -> None:
    responses = [
        MagicMock(fetchone=MagicMock(return_value=(123,))),
        MagicMock(fetchall=MagicMock(return_value=[("MOTHER", "female")])),
    ]
    with patch.object(api, "session", mock_session_with_responses(responses)):
        with pytest.raises(ValueError, match="sample 'CHILD' has no father"):
            await api.get_trio_by_index("CHILD")


@pytest.mark.asyncio
async def test_no_mother(api: NgsdApi) -> None:
    responses = [
        MagicMock(fetchone=MagicMock(return_value=(123,))),
        MagicMock(fetchall=MagicMock(return_value=[("FATHER", "male")])),
    ]
    with patch.object(api, "session", mock_session_with_responses(responses)):
        with pytest.raises(ValueError, match="sample 'CHILD' has no mother"):
            await api.get_trio_by_index("CHILD")
