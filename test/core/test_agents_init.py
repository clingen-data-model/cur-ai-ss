from unittest.mock import patch

from lib.core.agents_init import init_agents_sdk


def test_init_agents_sdk_disables_tracing():
    with patch('lib.core.agents_init.set_tracing_disabled') as mock_set:
        init_agents_sdk()

    mock_set.assert_called_once_with(True)
