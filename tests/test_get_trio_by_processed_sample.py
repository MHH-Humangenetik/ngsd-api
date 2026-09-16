"""Tests for NgsdApi.get_trio_by_processed_sample using mocked database responses."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ngsd_api import NgsdApi, NgsdSettings
from ngsd_api.types import Trio


def mock_session_with_responses(responses: list):
    """Create a mock session that returns the given responses in sequence."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=responses)

    @asynccontextmanager
    async def session_ctx():
        yield mock_session

    return session_ctx


@pytest.fixture
def api() -> NgsdApi:
    return NgsdApi(NgsdSettings(host="mock", password="mock"))


@pytest.mark.asyncio
async def test_complete_trio(api: NgsdApi) -> None:
    responses = [
        MagicMock(fetchone=MagicMock(return_value=(123, "ProjectA", "SystemX"))),
        MagicMock(fetchall=MagicMock(return_value=[("FATHER", "male"), ("MOTHER", "female")])),
        MagicMock(fetchall=MagicMock(return_value=[("FATHER", 2), ("MOTHER", 3)])),
    ]
    with patch.object(api, "session", mock_session_with_responses(responses)):
        trio = await api.get_trio_by_processed_sample("CHILD_01")
    assert trio == Trio(child="CHILD_01", father="FATHER_02", mother="MOTHER_03")


@pytest.mark.asyncio
async def test_invalid_format(api: NgsdApi) -> None:
    with pytest.raises(ValueError, match="invalid processed sample name 'NOSUFFIX'"):
        await api.get_trio_by_processed_sample("NOSUFFIX")


@pytest.mark.asyncio
async def test_no_processed_sample(api: NgsdApi) -> None:
    responses = [MagicMock(fetchone=MagicMock(return_value=None))]
    with patch.object(api, "session", mock_session_with_responses(responses)):
        with pytest.raises(ValueError, match="no processed sample named 'UNKNOWN_01'"):
            await api.get_trio_by_processed_sample("UNKNOWN_01")


@pytest.mark.asyncio
async def test_no_parents(api: NgsdApi) -> None:
    responses = [
        MagicMock(fetchone=MagicMock(return_value=(123, "ProjectA", "SystemX"))),
        MagicMock(fetchall=MagicMock(return_value=[])),
    ]
    with patch.object(api, "session", mock_session_with_responses(responses)):
        with pytest.raises(ValueError, match="sample 'ORPHAN' has no parents"):
            await api.get_trio_by_processed_sample("ORPHAN_01")


@pytest.mark.asyncio
async def test_no_father(api: NgsdApi) -> None:
    responses = [
        MagicMock(fetchone=MagicMock(return_value=(123, "ProjectA", "SystemX"))),
        MagicMock(fetchall=MagicMock(return_value=[("MOTHER", "female")])),
    ]
    with patch.object(api, "session", mock_session_with_responses(responses)):
        with pytest.raises(ValueError, match="sample 'CHILD' has no father"):
            await api.get_trio_by_processed_sample("CHILD_01")


@pytest.mark.asyncio
async def test_no_mother(api: NgsdApi) -> None:
    responses = [
        MagicMock(fetchone=MagicMock(return_value=(123, "ProjectA", "SystemX"))),
        MagicMock(fetchall=MagicMock(return_value=[("FATHER", "male")])),
    ]
    with patch.object(api, "session", mock_session_with_responses(responses)):
        with pytest.raises(ValueError, match="sample 'CHILD' has no mother"):
            await api.get_trio_by_processed_sample("CHILD_01")


@pytest.mark.asyncio
async def test_father_no_matching_processed_sample(api: NgsdApi) -> None:
    responses = [
        MagicMock(fetchone=MagicMock(return_value=(123, "ProjectA", "SystemX"))),
        MagicMock(fetchall=MagicMock(return_value=[("FATHER", "male"), ("MOTHER", "female")])),
        MagicMock(fetchall=MagicMock(return_value=[("MOTHER", 1)])),
    ]
    with patch.object(api, "session", mock_session_with_responses(responses)):
        with pytest.raises(ValueError, match="father 'FATHER' has no processed sample in project 'ProjectA'"):
            await api.get_trio_by_processed_sample("CHILD_01")


@pytest.mark.asyncio
async def test_mother_no_matching_processed_sample(api: NgsdApi) -> None:
    responses = [
        MagicMock(fetchone=MagicMock(return_value=(123, "ProjectA", "SystemX"))),
        MagicMock(fetchall=MagicMock(return_value=[("FATHER", "male"), ("MOTHER", "female")])),
        MagicMock(fetchall=MagicMock(return_value=[("FATHER", 1)])),
    ]
    with patch.object(api, "session", mock_session_with_responses(responses)):
        with pytest.raises(ValueError, match="mother 'MOTHER' has no processed sample in project 'ProjectA'"):
            await api.get_trio_by_processed_sample("CHILD_01")
