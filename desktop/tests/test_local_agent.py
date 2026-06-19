from aidrama_desktop.local_agent import build_agent_response


def test_local_agent_builds_open_media_response():
    opened = []

    status, headers, body = build_agent_response(
        "GET",
        "/open-media?platform=WECHAT_VIDEO&accountId=media-1",
        lambda platform, account_id: opened.append((platform, account_id)),
    )

    assert status == 200
    assert headers["Access-Control-Allow-Origin"] == "*"
    assert body == b'{"success": true}'
    assert opened == [("WECHAT_VIDEO", "media-1")]


def test_local_agent_rejects_unknown_path():
    status, headers, body = build_agent_response("GET", "/missing", lambda platform, account_id: None)

    assert status == 404
    assert headers["Access-Control-Allow-Origin"] == "*"
    assert body == b'{"success": false}'
