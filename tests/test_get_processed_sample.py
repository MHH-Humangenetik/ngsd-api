"""Tests for NgsdApi.get_processed_sample using mocked database responses."""

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
    return NgsdApi(NgsdSettings(host="mock", user="mock", password="mock"))


@pytest.mark.asyncio
async def test_found(api: NgsdApi) -> None:
    responses = [
        MagicMock(fetchone=MagicMock(return_value=("MyProject", "ssHAEv7", "#01234")))
    ]
    with patch.object(api, "session", mock_session_with_responses(responses)):
        ps = await api.get_processed_sample("307780PR1_03")
    assert ps == ProcessedSample(
        name="307780PR1_03",
        process_id=3,
        project="MyProject",
        processing_system="ssHAEv7",
        run="#01234",
    )


@pytest.mark.asyncio
async def test_not_found(api: NgsdApi) -> None:
    responses = [MagicMock(fetchone=MagicMock(return_value=None))]
    with patch.object(api, "session", mock_session_with_responses(responses)):
        with pytest.raises(ValueError, match="no processed sample"):
            await api.get_processed_sample("307780PR1_03")


@pytest.mark.asyncio
async def test_invalid_name(api: NgsdApi) -> None:
    with pytest.raises(ValueError, match="invalid processed sample name"):
        await api.get_processed_sample("307780PR1")
