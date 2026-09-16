"""Tests for NgsdApi.get_processed_sample_folder using mocked database responses."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ngsd_api import NgsdApi, NgsdSettings


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


@pytest.fixture
def api_with_base() -> NgsdApi:
    return NgsdApi(NgsdSettings(host="mock", password="mock", projects_base="/data/projects"))


@pytest.mark.asyncio
async def test_path_without_base(api: NgsdApi) -> None:
    responses = [MagicMock(fetchone=MagicMock(return_value=("MyProject", "diagnostic", None)))]
    with patch.object(api, "session", mock_session_with_responses(responses)):
        path = await api.get_processed_sample_folder("SAMPLE_01")
    assert path == "/diagnostic/MyProject/SAMPLE_01"


@pytest.mark.asyncio
async def test_path_with_base(api_with_base: NgsdApi) -> None:
    responses = [MagicMock(fetchone=MagicMock(return_value=("MyProject", "research", None)))]
    with patch.object(api_with_base, "session", mock_session_with_responses(responses)):
        path = await api_with_base.get_processed_sample_folder("SAMPLE_03")
    assert path == "/data/projects/research/MyProject/SAMPLE_03"


@pytest.mark.asyncio
async def test_path_with_folder_override(api: NgsdApi) -> None:
    responses = [MagicMock(fetchone=MagicMock(return_value=("MyProject", "research", "/custom/path")))]
    with patch.object(api, "session", mock_session_with_responses(responses)):
        path = await api.get_processed_sample_folder("SAMPLE_02")
    assert path == "/custom/path/SAMPLE_02"


@pytest.mark.asyncio
async def test_invalid_format(api: NgsdApi) -> None:
    with pytest.raises(ValueError, match="invalid processed sample name 'NOSUFFIX'"):
        await api.get_processed_sample_folder("NOSUFFIX")


@pytest.mark.asyncio
async def test_nonexistent_sample(api: NgsdApi) -> None:
    responses = [MagicMock(fetchone=MagicMock(return_value=None))]
    with patch.object(api, "session", mock_session_with_responses(responses)):
        with pytest.raises(ValueError, match="no processed sample named 'UNKNOWN_99'"):
            await api.get_processed_sample_folder("UNKNOWN_99")
