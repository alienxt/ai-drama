package com.onehot.aidrama.ai;

import com.onehot.aidrama.configs.SystemConfigService;
import com.sun.net.httpserver.Headers;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.web.client.RestClient;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class AiServiceTest {
    @Test
    void defaultProviderUsesOfficialOpenAiConfigWithoutThirdPartyHeaders() throws Exception {
        try (TestOpenAiServer server = TestOpenAiServer.start(
                "/responses",
                """
                        {"output_text":"official-ok"}
                        """
        )) {
            AiService service = service(Map.of(
                    "openai.baseUrl", server.baseUrl(),
                    "openai.apiKey", "official-key",
                    "openai.textModel", "official-text-model",
                    "openai.thirdParty.apiKey", "third-party-key",
                    "openai.thirdParty.extraHeaders", "x-openai-actor-authorization: local-image-extension"
            ));

            String result = service.generateText("system", "user");

            assertThat(result).isEqualTo("official-ok");
            CapturedRequest request = server.request();
            assertThat(request.path()).isEqualTo("/responses");
            assertThat(request.header(HttpHeaders.AUTHORIZATION)).isEqualTo("Bearer official-key");
            assertThat(request.header("x-openai-actor-authorization")).isNull();
            assertThat(request.body()).contains("\"model\":\"official-text-model\"");
            assertThat(request.body()).doesNotContain("\"store\":false");
        }
    }

    @Test
    void thirdPartyProviderUsesSeparateConfigHeadersAndResponseStorageSetting() throws Exception {
        try (TestOpenAiServer server = TestOpenAiServer.start(
                "/v1/responses",
                """
                        {"output":[{"type":"message","content":[{"type":"output_text","text":"third-party-ok"}]}]}
                        """
        )) {
            AiService service = service(Map.of(
                    "openai.provider", "thirdParty",
                    "openai.apiKey", "official-key",
                    "openai.baseUrl", "http://127.0.0.1:1",
                    "openai.thirdParty.baseUrl", server.baseUrl() + "/v1",
                    "openai.thirdParty.apiKey", "third-party-key",
                    "openai.thirdParty.textModel", "third-party-text-model",
                    "openai.thirdParty.extraHeaders", """
                            x-openai-actor-authorization: local-image-extension
                            x-custom-header=custom-value
                            Authorization: ignored
                            """,
                    "openai.thirdParty.disableResponseStorage", "true"
            ));

            String result = service.generateText("system", "user");

            assertThat(result).isEqualTo("third-party-ok");
            assertThat(service.textModel()).isEqualTo("third-party-text-model");
            CapturedRequest request = server.request();
            assertThat(request.path()).isEqualTo("/v1/responses");
            assertThat(request.header(HttpHeaders.AUTHORIZATION)).isEqualTo("Bearer third-party-key");
            assertThat(request.header("x-openai-actor-authorization")).isEqualTo("local-image-extension");
            assertThat(request.header("x-custom-header")).isEqualTo("custom-value");
            assertThat(request.body()).contains("\"model\":\"third-party-text-model\"");
            assertThat(request.body()).contains("\"store\":false");
        }
    }

    @Test
    void thirdPartyProviderUsesSeparateImageConfig() throws Exception {
        try (TestOpenAiServer server = TestOpenAiServer.start(
                "/v1/images/generations",
                """
                        {"data":[{"b64_json":"image-base64"}]}
                        """
        )) {
            AiService service = service(Map.of(
                    "openai.provider", "tokenfree",
                    "openai.thirdParty.baseUrl", server.baseUrl() + "/v1",
                    "openai.thirdParty.apiKey", "third-party-key",
                    "openai.thirdParty.imageModel", "third-party-image-model",
                    "openai.thirdParty.imageSize", "512x768",
                    "openai.thirdParty.imageQuality", "low",
                    "openai.thirdParty.imageOutputFormat", "png",
                    "openai.thirdParty.extraHeaders", "x-openai-actor-authorization: local-image-extension"
            ));

            String result = service.generateImageBase64("prompt");

            assertThat(result).isEqualTo("image-base64");
            assertThat(service.imageModel()).isEqualTo("third-party-image-model");
            assertThat(service.imageSize()).isEqualTo("512x768");
            CapturedRequest request = server.request();
            assertThat(request.path()).isEqualTo("/v1/images/generations");
            assertThat(request.header(HttpHeaders.AUTHORIZATION)).isEqualTo("Bearer third-party-key");
            assertThat(request.header("x-openai-actor-authorization")).isEqualTo("local-image-extension");
            assertThat(request.body()).contains("\"model\":\"third-party-image-model\"");
            assertThat(request.body()).contains("\"size\":\"512x768\"");
            assertThat(request.body()).contains("\"quality\":\"low\"");
            assertThat(request.body()).contains("\"output_format\":\"png\"");
        }
    }

    @Test
    void switchingBackToOfficialDoesNotReuseThirdPartyHeaders() throws Exception {
        Map<String, String> configs = new LinkedHashMap<>();
        try (
                TestOpenAiServer thirdParty = TestOpenAiServer.start(
                        "/v1/responses",
                        """
                                {"output":[{"type":"message","content":[{"type":"output_text","text":"third-party-ok"}]}]}
                                """
                );
                TestOpenAiServer official = TestOpenAiServer.start(
                        "/responses",
                        """
                                {"output_text":"official-ok"}
                                """
                )
        ) {
            configs.put("openai.provider", "thirdParty");
            configs.put("openai.thirdParty.baseUrl", thirdParty.baseUrl() + "/v1");
            configs.put("openai.thirdParty.apiKey", "third-party-key");
            configs.put("openai.thirdParty.extraHeaders", "x-openai-actor-authorization: local-image-extension");
            AiService service = service(configs);

            assertThat(service.generateText("system", "user")).isEqualTo("third-party-ok");

            configs.clear();
            configs.put("openai.provider", "official");
            configs.put("openai.baseUrl", official.baseUrl());
            configs.put("openai.apiKey", "official-key");

            assertThat(service.generateText("system", "user")).isEqualTo("official-ok");
            CapturedRequest request = official.request();
            assertThat(request.header(HttpHeaders.AUTHORIZATION)).isEqualTo("Bearer official-key");
            assertThat(request.header("x-openai-actor-authorization")).isNull();
        }
    }

    @Test
    void failedThirdPartyRequestIncludesProviderStatusAndErrorCode() throws Exception {
        try (TestOpenAiServer server = TestOpenAiServer.start(
                "/v1/responses",
                400,
                """
                        {"code":"API_KEY_REQUIRED","message":"API key is required"}
                        """
        )) {
            AiService service = service(Map.of(
                    "openai.provider", "thirdParty",
                    "openai.thirdParty.baseUrl", server.baseUrl() + "/v1",
                    "openai.thirdParty.apiKey", "bad-key"
            ));

            assertThatThrownBy(() -> service.generateText("system", "user"))
                    .isInstanceOf(OpenAiException.class)
                    .hasMessageContaining("provider=thirdParty")
                    .hasMessageContaining("path=/responses")
                    .hasMessageContaining("status=400")
                    .hasMessageContaining("code=API_KEY_REQUIRED")
                    .hasMessageContaining("API key is required");
        }
    }

    private AiService service(Map<String, String> configs) {
        SystemConfigService configService = mock(SystemConfigService.class);
        when(configService.get(anyString())).thenAnswer(invocation -> {
            String key = invocation.getArgument(0);
            return Optional.ofNullable(configs.get(key));
        });
        return new AiService(configService, RestClient.builder());
    }

    private record CapturedRequest(String path, Headers headers, String body) {
        String header(String name) {
            List<String> values = headers.get(name);
            if (values == null || values.isEmpty()) {
                return null;
            }
            return values.getFirst();
        }
    }

    private static class TestOpenAiServer implements AutoCloseable {
        private final HttpServer server;
        private final AtomicReference<CapturedRequest> request = new AtomicReference<>();

        private TestOpenAiServer(HttpServer server) {
            this.server = server;
        }

        static TestOpenAiServer start(String path, String responseBody) throws IOException {
            return start(path, 200, responseBody);
        }

        static TestOpenAiServer start(String path, int status, String responseBody) throws IOException {
            HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            TestOpenAiServer testServer = new TestOpenAiServer(server);
            server.createContext(path, exchange -> testServer.handle(exchange, status, responseBody));
            server.start();
            return testServer;
        }

        String baseUrl() {
            return "http://127.0.0.1:" + server.getAddress().getPort();
        }

        CapturedRequest request() {
            return request.get();
        }

        private void handle(HttpExchange exchange, int status, String responseBody) throws IOException {
            String body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
            Headers headers = new Headers();
            headers.putAll(exchange.getRequestHeaders());
            request.set(new CapturedRequest(exchange.getRequestURI().getPath(), headers, body));
            byte[] response = responseBody.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(status, response.length);
            exchange.getResponseBody().write(response);
            exchange.close();
        }

        @Override
        public void close() {
            server.stop(0);
        }
    }
}
