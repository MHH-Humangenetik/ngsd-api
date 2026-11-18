"""Tests for NgsdApi.get_processed_samples_by_sample_name using mocked database responses."""

from contextlib import asynccontextmanager
from datetime import date
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
    return NgsdApi(NgsdSettings(host="mock", user="mock", password="mock"))


@pytest.mark.asyncio
async def test_all_processed_samples(api: NgsdApi) -> None:
    responses = [
        MagicMock(fetchone=MagicMock(return_value=(123,))),
        MagicMock(
            fetchall=MagicMock(
                return_value=[
                    (
                        1,
                        "ProjectA",
                        "SystemX",
                        "RUN1",
                        11,
                        "WGS",
                        "bad",
                        0,
                        date(2026, 4, 17),
                        date(2026, 4, 19),
                    ),
                    (2, "ProjectA", "SystemY", None, 12, "lrGS", "n/a", 1, None, None),
                ]
            )
        ),
        MagicMock(
            fetchall=MagicMock(
                return_value=[
                    (11, "target region read depth", "float", "40.2"),
                    (11, "target region 20x percentage", "float", "99.48"),
                    (12, "target region read depth", "float", "n/a"),
                ]
            )
        ),
    ]
    with patch.object(api, "session", mock_session_with_responses(responses)):
        samples = await api.get_processed_samples_by_sample_name("SAMPLE")
    assert samples == [
        ProcessedSample(
            name="SAMPLE_01",
            process_id=1,
            project="ProjectA",
            processing_system="SystemX",
            run="RUN1",
            processing_system_type="WGS",
            quality="bad",
            scheduled_for_resequencing=False,
            run_start_date=date(2026, 4, 17),
            run_end_date=date(2026, 4, 19),
            qc={
                "target region read depth": 40.2,
                "target region 20x percentage": 99.48,
            },
        ),
        ProcessedSample(
            name="SAMPLE_02",
            process_id=2,
            project="ProjectA",
            processing_system="SystemY",
            processing_system_type="lrGS",
            quality="n/a",
            scheduled_for_resequencing=True,
            qc={"target region read depth": "n/a"},
        ),
    ]


@pytest.mark.asyncio
async def test_filter_by_project(api: NgsdApi) -> None:
    responses = [
        MagicMock(fetchone=MagicMock(return_value=(123,))),
        MagicMock(
            fetchall=MagicMock(
                return_value=[
                    (1, "ProjectA", "SystemX", "RUN1", 1, "WGS", "good", 0, None, None)
                ]
            )
        ),
        MagicMock(fetchall=MagicMock(return_value=[])),
    ]
    with patch.object(api, "session", mock_session_with_responses(responses)):
        samples = await api.get_processed_samples_by_sample_name(
            "SAMPLE", project="ProjectA"
        )
    assert len(samples) == 1
    assert samples[0].project == "ProjectA"


@pytest.mark.asyncio
async def test_filter_by_processing_system(api: NgsdApi) -> None:
    responses = [
        MagicMock(fetchone=MagicMock(return_value=(123,))),
        MagicMock(
            fetchall=MagicMock(
                return_value=[
                    (2, "ProjectA", "SystemY", "RUN2", 1, "WGS", "good", 0, None, None)
                ]
            )
        ),
        MagicMock(fetchall=MagicMock(return_value=[])),
    ]
    with patch.object(api, "session", mock_session_with_responses(responses)):
        samples = await api.get_processed_samples_by_sample_name(
            "SAMPLE", processing_system="SystemY"
        )
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
        samples = await api.get_processed_samples_by_sample_name(
            "SAMPLE", project="NonexistentProject"
        )
    assert samples == []
