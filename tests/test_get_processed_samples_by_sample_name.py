"""Tests for NgsdApi.get_processed_samples_by_sample_name using mocked database responses."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ngsd_api import NgsdApi, NgsdSettings
from ngsd_api.types import ProcessedSample


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
async def test_all_processed_samples(api: NgsdApi) -> None:
    responses = [
        MagicMock(fetchone=MagicMock(return_value=(123,))),
        MagicMock(fetchall=MagicMock(return_value=[
            (1, "ProjectA", "SystemX"),
            (2, "ProjectA", "SystemY"),
        ])),
    ]
    with patch.object(api, "session", mock_session_with_responses(responses)):
        samples = await api.get_processed_samples_by_sample_name("SAMPLE")
    assert samples == [
        ProcessedSample(name="SAMPLE_01", process_id=1, project="ProjectA", processing_system="SystemX"),
        ProcessedSample(name="SAMPLE_02", process_id=2, project="ProjectA", processing_system="SystemY"),
    ]


@pytest.mark.asyncio
async def test_filter_by_project(api: NgsdApi) -> None:
    responses = [
        MagicMock(fetchone=MagicMock(return_value=(123,))),
        MagicMock(fetchall=MagicMock(return_value=[(1, "ProjectA", "SystemX")])),
    ]
    with patch.object(api, "session", mock_session_with_responses(responses)):
        samples = await api.get_processed_samples_by_sample_name("SAMPLE", project="ProjectA")
    assert len(samples) == 1
    assert samples[0].project == "ProjectA"


@pytest.mark.asyncio
async def test_filter_by_processing_system(api: NgsdApi) -> None:
    responses = [
        MagicMock(fetchone=MagicMock(return_value=(123,))),
        MagicMock(fetchall=MagicMock(return_value=[(2, "ProjectA", "SystemY")])),
    ]
    with patch.object(api, "session", mock_session_with_responses(responses)):
        samples = await api.get_processed_samples_by_sample_name("SAMPLE", processing_system="SystemY")
    assert len(samples) == 1
    assert samples[0].processing_system == "SystemY"


@pytest.mark.asyncio
async def test_no_sample(api: NgsdApi) -> None:
    responses = [MagicMock(fetchone=MagicMock(return_value=None))]
    with patch.object(api, "session", mock_session_with_responses(responses)):
        with pytest.raises(ValueError, match="no sample named 'UNKNOWN'"):
            await api.get_processed_samples_by_sample_name("UNKNOWN")


@pytest.mark.asyncio
async def test_empty_result(api: NgsdApi) -> None:
    responses = [
        MagicMock(fetchone=MagicMock(return_value=(123,))),
        MagicMock(fetchall=MagicMock(return_value=[])),
    ]
    with patch.object(api, "session", mock_session_with_responses(responses)):
        samples = await api.get_processed_samples_by_sample_name("SAMPLE", project="NonexistentProject")
    assert samples == []
