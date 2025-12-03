from unittest.mock import MagicMock, patch

import pytest
import requests
from pytest import raises

from lib.evagg.utils import RequestsWebContentClient


def test_settings():
    web_client = RequestsWebContentClient()
    web_client.update_settings(
        max_retries=1,
        retry_backoff=2,
        retry_codes=[500, 429],
        no_raise_codes=[422],
        content_type="json",
    )
    settings = web_client._settings.dict()
    assert settings["max_retries"] == 1
    assert settings["retry_backoff"] == 2
    assert settings["retry_codes"] == [500, 429]
    assert settings["no_raise_codes"] == [422]
    assert settings["content_type"] == "json"

    web_client.update_settings(max_retries=10)
    settings = web_client._settings.dict()
    assert settings["max_retries"] == 10
    assert settings["retry_backoff"] == 2

    with raises(ValueError):
        web_client.update_settings(invalid=1)


@patch("requests.sessions.Session.request")
def test_get_content_types(mock_request):
    mock_request.side_effect = [
        MagicMock(status_code=200, text="test"),
        MagicMock(status_code=200, text="<test>1</test>"),
        MagicMock(status_code=200, text='{"test": 1}'),
        MagicMock(status_code=200, text='{"test": 1}'),
    ]

    with raises(ValueError):
        RequestsWebContentClient(settings={"content_type": "binary"})

    web_client = RequestsWebContentClient()
    assert (
        web_client.get(
            "https://any.url/testing", content_type="text", params={"extra": ""}
        )
        == "test"
    )
    assert mock_request.call_args.args[1] == "https://any.url/testing"
    assert mock_request.call_args.kwargs["params"] == {"extra": ""}
    assert web_client.get("https://any.url/testing", content_type="xml").tag == "test"  # type: ignore
    assert web_client.get("https://any.url/testing", content_type="json") == {"test": 1}
    with raises(ValueError):
        web_client.get("https://any.url/testing", content_type="invalid")


@patch("urllib3.connectionpool.HTTPConnectionPool._get_conn")
def test_retry_succeeded(mock_get_conn):
    mock_get_conn.return_value.getresponse.side_effect = [
        MagicMock(status=500, headers={}, iter_content=lambda _: [b""]),
        MagicMock(status=429, headers={}, iter_content=lambda _: [b""]),
        MagicMock(status=200, headers={}, iter_content=lambda _: [b""]),
    ]

    settings = {"max_retries": 2, "retry_backoff": 0, "retry_codes": [500, 429]}
    web_client = RequestsWebContentClient(settings)
    web_client.get("https://any.url/testing")

    assert mock_get_conn.return_value.request.call_args.args[0] == "GET"
    assert mock_get_conn.return_value.request.call_args.args[1] == "/testing"
    assert len(mock_get_conn.return_value.request.mock_calls) == 3


@patch("urllib3.connectionpool.HTTPConnectionPool._get_conn")
def test_retry_failed(mock_get_conn):
    mock_get_conn.return_value.getresponse.side_effect = [
        MagicMock(status=429, headers={}, iter_content=lambda _: [b""]),
        MagicMock(status=500, headers={}, iter_content=lambda _: [b""]),
    ]

    settings = {"max_retries": 1, "retry_backoff": 0, "retry_codes": [500, 429]}
    web_client = RequestsWebContentClient(settings)
    with raises(requests.exceptions.RetryError):
        web_client.get("https://any.url/testing")
