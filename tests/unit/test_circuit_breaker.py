import pytest
from unittest.mock import AsyncMock, patch
from backend.resilience.circuit_breaker import CircuitBreaker, CircuitOpenError

@pytest.fixture
def mock_redis():
    mock = AsyncMock()
    # By default, mock redis returns state="closed"
    mock.get.side_effect = lambda k: "closed" if "state" in k else None
    return mock

@pytest.fixture
def circuit_breaker(mock_redis):
    with patch("backend.resilience.circuit_breaker.aioredis.from_url", return_value=mock_redis):
        return CircuitBreaker(name="test_cb", failure_threshold=3, recovery_timeout=60)

@pytest.mark.asyncio
async def test_initial_state_is_closed(circuit_breaker, mock_redis):
    async with circuit_breaker:
        pass  # should not raise

@pytest.mark.asyncio
async def test_circuit_open_raises_error(circuit_breaker, mock_redis):
    def mock_get(key):
        if "state" in key: return "open"
        if "opened_at" in key: return "9999999999.0"  # Far in the future
        return None
    mock_redis.get.side_effect = mock_get

    with pytest.raises(CircuitOpenError):
        async with circuit_breaker:
            pass

@pytest.mark.asyncio
async def test_record_failure(circuit_breaker, mock_redis):
    mock_redis.incr.return_value = 1
    try:
        async with circuit_breaker:
            raise ValueError("Test failure")
    except ValueError:
        pass
    mock_redis.incr.assert_called_with("circuit:test_cb:failure_count")

@pytest.mark.asyncio
async def test_record_success_resets_failures(circuit_breaker, mock_redis):
    async with circuit_breaker:
        pass
    mock_redis.set.assert_called_with("circuit:test_cb:failure_count", 0)

@pytest.mark.asyncio
async def test_failure_threshold_trips_breaker(circuit_breaker, mock_redis):
    mock_redis.incr.return_value = 3
    try:
        async with circuit_breaker:
            raise ValueError("Test failure")
    except ValueError:
        pass
    mock_redis.set.assert_any_call("circuit:test_cb:state", "open")
