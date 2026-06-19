package com.onehot.aidrama.baiduyun;

import org.junit.jupiter.api.Test;

import java.net.URI;
import java.util.Map;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

class BaiduPanHttpClientTest {
    @Test
    void encodesAmpersandInDirectoryQueryParameter() {
        URI uri = BaiduPanHttpClient.listDirectoryUri(
                "/drama/真人剧/2026/6月18日/1.取款当天（61集）尹洋&邹倩",
                "token-value"
        );

        assertThat(uri.toASCIIString()).contains("%26");
        assertThat(uri.toASCIIString()).doesNotContain("尹洋&邹倩");
    }

    @Test
    void masksAccessTokenWhenReportingBaiduRequestUri() {
        URI uri = URI.create("https://pan.baidu.com/rest/2.0/xpan/file?method=list&access_token=secret-token&refresh_token=refresh-secret&client_secret=client-secret&dir=/root");

        assertThat(BaiduPanHttpClient.safeUri(uri))
                .contains("access_token=***")
                .contains("refresh_token=***")
                .contains("client_secret=***")
                .doesNotContain("secret-token")
                .doesNotContain("refresh-secret")
                .doesNotContain("client-secret");
    }

    @Test
    void resolvesEnabledSocks5ProxyFromSystemConfig() {
        Map<String, String> config = Map.of(
                "baidu.proxyEnabled", "true",
                "baidu.proxyHost", "127.0.0.1",
                "baidu.proxyPort", "1080",
                "baidu.proxyUsername", "proxy-user",
                "baidu.proxyPassword", "proxy-pass"
        );

        Optional<BaiduPanHttpClient.ProxySettings> settings = BaiduPanHttpClient.resolveProxySettings(key -> Optional.ofNullable(config.get(key)));

        assertThat(settings).isPresent();
        assertThat(settings.get().host()).isEqualTo("127.0.0.1");
        assertThat(settings.get().port()).isEqualTo(1080);
        assertThat(settings.get().username()).isEqualTo("proxy-user");
        assertThat(settings.get().password()).isEqualTo("proxy-pass");
    }

    @Test
    void ignoresProxyWhenDisabledOrIncomplete() {
        assertThat(BaiduPanHttpClient.resolveProxySettings(key -> Optional.empty())).isEmpty();
        assertThat(BaiduPanHttpClient.resolveProxySettings(key -> Optional.of("true"))).isEmpty();
    }
}
