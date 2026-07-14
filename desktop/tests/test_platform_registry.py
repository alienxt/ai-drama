from aidrama_desktop.browser.chrome import ChromeController
from aidrama_desktop.platforms.registry import get_publisher
from aidrama_desktop.platforms.tiktok import TikTokPublisher
from aidrama_desktop.platforms.wechat_video import WeChatVideoPublisher


def test_wechat_video_registry(tmp_path):
    publisher = get_publisher("WECHAT_VIDEO", ChromeController("chrome", tmp_path))

    assert isinstance(publisher, WeChatVideoPublisher)


def test_tiktok_registry(tmp_path):
    publisher = get_publisher("TIKTOK", ChromeController("chrome", tmp_path))

    assert isinstance(publisher, TikTokPublisher)
