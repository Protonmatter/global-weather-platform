from weather_platform.api import main


def test_request_identity_helper_exists() -> None:
    assert callable(main._request_id_from_request)
