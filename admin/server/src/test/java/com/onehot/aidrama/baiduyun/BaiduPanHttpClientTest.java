package com.onehot.aidrama.baiduyun;

import com.onehot.aidrama.configs.SystemConfigService;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

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
    void createsEncodedBaiduStreamingM3u8Uri() {
        URI uri = BaiduPanHttpClient.streamingUri(
                "/drama/真人剧/2026/6月18日/1.取款当天（61集）尹洋&邹倩/1.mp4",
                "token-value",
                "M3U8_AUTO_720"
        );

        assertThat(uri.toASCIIString()).contains("method=streaming");
        assertThat(uri.toASCIIString()).contains("type=M3U8_AUTO_720");
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

    @Test
    void refreshesAccessTokenAndRetriesListDirectoryWhenBaiduReportsExpiredToken() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        AtomicInteger listCalls = new AtomicInteger();
        server.createContext("/xpan/file", exchange -> {
            listCalls.incrementAndGet();
            String query = exchange.getRequestURI().getRawQuery();
            if (query != null && query.contains("access_token=old-token")) {
                respond(exchange, 200, "{\"errno\":-6}");
                return;
            }
            respond(
                    exchange,
                    200,
                    "{\"errno\":0,\"list\":[{\"path\":\"/root/new\",\"server_filename\":\"new\",\"isdir\":1,\"fs_id\":123,\"size\":0}]}"
            );
        });
        server.createContext("/oauth/token", exchange -> respond(
                exchange,
                200,
                "{\"access_token\":\"new-token\",\"refresh_token\":\"rotated-refresh\",\"expires_in\":2592000}"
        ));
        server.start();
        try {
            Map<String, String> config = baiduConfig();
            BaiduPanHttpClient client = client(config, server);

            List<BaiduPanEntry> entries = client.listDirectory("/root");

            assertThat(entries).hasSize(1);
            assertThat(entries.getFirst().path()).isEqualTo("/root/new");
            assertThat(listCalls).hasValue(2);
            assertThat(config.get("baidu.accessToken")).isEqualTo("new-token");
            assertThat(config.get("baidu.refreshToken")).isEqualTo("rotated-refresh");
        } finally {
            server.stop(0);
        }
    }

    @Test
    void reportsRefreshTokenFailureWithOauthMessage() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/oauth/token", exchange -> respond(
                exchange,
                400,
                "{\"error\":\"expired_token\",\"error_description\":\"refresh token has been used\"}"
        ));
        server.start();
        try {
            Map<String, String> config = baiduConfig();
            config.put("baidu.tokenObtainedAt", "0");
            config.put("baidu.expiresIn", "0");
            BaiduPanHttpClient client = client(config, server);

            assertThatThrownBy(() -> client.listDirectory("/root"))
                    .isInstanceOf(BaiduPanException.class)
                    .hasMessageContaining("Baidu token refresh failed")
                    .hasMessageContaining("expired_token")
                    .hasMessageContaining("refresh token has been used");
        } finally {
            server.stop(0);
        }
    }

    @Test
    void keepsUsingExistingAccessTokenWhenRefreshFailsButTokenStillWorks() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        AtomicInteger listCalls = new AtomicInteger();
        server.createContext("/xpan/file", exchange -> {
            listCalls.incrementAndGet();
            respond(
                    exchange,
                    200,
                    "{\"errno\":0,\"list\":[{\"path\":\"/root/old\",\"server_filename\":\"old\",\"isdir\":1,\"fs_id\":123,\"size\":0}]}"
            );
        });
        server.createContext("/oauth/token", exchange -> respond(exchange, 503, "unavailable", "text/plain"));
        server.start();
        try {
            Map<String, String> config = baiduConfig();
            config.put("baidu.tokenObtainedAt", "0");
            config.put("baidu.expiresIn", "0");
            BaiduPanHttpClient client = client(config, server);

            List<BaiduPanEntry> entries = client.listDirectory("/root");

            assertThat(entries).hasSize(1);
            assertThat(entries.getFirst().path()).isEqualTo("/root/old");
            assertThat(listCalls).hasValue(2);
            assertThat(config.get("baidu.accessToken")).isEqualTo("old-token");
        } finally {
            server.stop(0);
        }
    }

    @Test
    void refreshesAccessTokenAndRetriesReadUrlWhenBaiduReportsExpiredToken() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        AtomicInteger resourceCalls = new AtomicInteger();
        server.createContext("/resource", exchange -> {
            resourceCalls.incrementAndGet();
            String query = exchange.getRequestURI().getRawQuery();
            if (query != null && query.contains("access_token=old-token")) {
                respond(exchange, 200, "{\"errno\":\"111\",\"errmsg\":\"Access token expired\"}");
                return;
            }
            respond(exchange, 200, "#EXTM3U\n#EXT-X-ENDLIST\n", "application/vnd.apple.mpegurl");
        });
        server.createContext("/oauth/token", exchange -> respond(
                exchange,
                200,
                "{\"access_token\":\"new-token\",\"refresh_token\":\"rotated-refresh\",\"expires_in\":2592000}"
        ));
        server.start();
        try {
            Map<String, String> config = baiduConfig();
            BaiduPanHttpClient client = client(config, server);

            String body = client.readUrl(baseUrl(server) + "/resource?access_token=old-token&path=/root/1.mp4");

            assertThat(body).contains("#EXTM3U");
            assertThat(resourceCalls).hasValue(2);
            assertThat(config.get("baidu.accessToken")).isEqualTo("new-token");
        } finally {
            server.stop(0);
        }
    }

    private static Map<String, String> baiduConfig() {
        Map<String, String> config = new HashMap<>();
        config.put("baidu.accessToken", "old-token");
        config.put("baidu.refreshToken", "old-refresh");
        config.put("baidu.clientId", "client-id");
        config.put("baidu.clientSecret", "client-secret");
        config.put("baidu.tokenObtainedAt", String.valueOf(Instant.now().getEpochSecond()));
        config.put("baidu.expiresIn", "2592000");
        return config;
    }

    private static BaiduPanHttpClient client(Map<String, String> config, HttpServer server) {
        SystemConfigService configService = mock(SystemConfigService.class);
        when(configService.get(anyString())).thenAnswer(invocation ->
                Optional.ofNullable(config.get(invocation.getArgument(0)))
        );
        when(configService.require(anyString())).thenAnswer(invocation -> {
            String key = invocation.getArgument(0);
            String value = config.get(key);
            if (value == null) {
                throw new IllegalStateException("Missing system config: " + key);
            }
            return value;
        });
        when(configService.put(anyString(), anyString(), anyBoolean())).thenAnswer(invocation -> {
            config.put(invocation.getArgument(0), invocation.getArgument(1));
            return null;
        });
        String baseUrl = baseUrl(server);
        return new BaiduPanHttpClient(
                configService,
                baseUrl + "/oauth/token",
                baseUrl + "/xpan/file",
                baseUrl + "/xpan/multimedia"
        );
    }

    private static void respond(HttpExchange exchange, int statusCode, String body) throws IOException {
        respond(exchange, statusCode, body, "application/json; charset=utf-8");
    }

    private static void respond(
            HttpExchange exchange,
            int statusCode,
            String body,
            String contentType
    ) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().add("Content-Type", contentType);
        exchange.sendResponseHeaders(statusCode, bytes.length);
        exchange.getResponseBody().write(bytes);
        exchange.close();
    }

    private static String baseUrl(HttpServer server) {
        return "http://127.0.0.1:" + server.getAddress().getPort();
    }
}
