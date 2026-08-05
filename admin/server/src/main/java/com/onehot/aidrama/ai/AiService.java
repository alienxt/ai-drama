package com.onehot.aidrama.ai;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.onehot.aidrama.configs.SystemConfigService;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class AiService {
    private static final Logger LOGGER = LoggerFactory.getLogger(AiService.class);
    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();
    private static final String DEFAULT_BASE_URL = "https://api.openai.com/v1";
    private static final String DEFAULT_THIRD_PARTY_BASE_URL = "https://tokenfree.biz/v1";
    private static final String PROVIDER_OFFICIAL = "official";
    private static final String PROVIDER_THIRD_PARTY = "thirdParty";
    public static final String DEFAULT_TEXT_MODEL = "gpt-5.5";
    public static final String DEFAULT_IMAGE_MODEL = "gpt-image-2";
    public static final String DEFAULT_IMAGE_SIZE = "1024x1536";
    public static final String DEFAULT_VIDEO_COVER_IMAGE_SIZE = "1536x1024";
    public static final String DEFAULT_IMAGE_QUALITY = "medium";
    public static final String DEFAULT_IMAGE_FORMAT = "jpeg";

    private final SystemConfigService configService;
    private final RestClient.Builder restClientBuilder;

    public AiService(SystemConfigService configService, RestClient.Builder restClientBuilder) {
        this.configService = configService;
        this.restClientBuilder = restClientBuilder;
    }

    public String generateText(String systemPrompt, String userPrompt) {
        AiProvider provider = provider();
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("model", textModel(provider));
        body.put("instructions", systemPrompt);
        body.put("input", userPrompt);
        body.put("text", Map.of("verbosity", "low"));
        if (provider == AiProvider.THIRD_PARTY && configBoolean("openai.thirdParty.disableResponseStorage", true)) {
            body.put("store", false);
        }
        JsonNode response = post(
                provider,
                "/responses",
                body
        );
        String outputText = response.path("output_text").asText("");
        if (!outputText.isBlank()) {
            return outputText.trim();
        }
        String nestedText = firstTextFromOutput(response);
        if (!nestedText.isBlank()) {
            return nestedText.trim();
        }
        throw new OpenAiException("OpenAI 文本模型未返回内容");
    }

    public String generateImageBase64(String prompt) {
        return generateImageBase64(prompt, imageSize());
    }

    public String generateImageBase64(String prompt, String size) {
        AiProvider provider = provider();
        JsonNode response = post(
                provider,
                "/images/generations",
                Map.of(
                        "model", imageModel(provider),
                        "prompt", prompt,
                        "n", 1,
                        "size", size == null || size.isBlank() ? DEFAULT_IMAGE_SIZE : size,
                        "quality", imageQuality(provider),
                        "output_format", imageOutputFormat(provider)
                )
        );
        String image = response.path("data").path(0).path("b64_json").asText("");
        if (!image.isBlank()) {
            return image;
        }
        throw new OpenAiException("OpenAI 图片模型未返回图片");
    }

    public String textModel() {
        return textModel(provider());
    }

    public String imageModel() {
        return imageModel(provider());
    }

    public String imageSize() {
        return configForProvider("openai.imageSize", "openai.thirdParty.imageSize", DEFAULT_IMAGE_SIZE);
    }

    public String videoCoverImageSize() {
        return configForProvider(
                "openai.videoCoverImageSize",
                "openai.thirdParty.videoCoverImageSize",
                DEFAULT_VIDEO_COVER_IMAGE_SIZE
        );
    }

    public String imageQuality() {
        return imageQuality(provider());
    }

    public String imageOutputFormat() {
        return imageOutputFormat(provider());
    }

    private JsonNode post(AiProvider provider, String path, Object body) {
        String baseUrl = baseUrl(provider);
        String model = requestModel(body);
        long startedAt = System.nanoTime();
        LOGGER.info(
                "OpenAI request started: provider={}, baseUrl={}, path={}, model={}",
                provider.configValue(),
                baseUrl,
                path,
                model
        );
        try {
            JsonNode response = client(provider, baseUrl)
                    .post()
                    .uri(path)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(body)
                    .retrieve()
                    .body(JsonNode.class);
            LOGGER.info(
                    "OpenAI request succeeded: provider={}, baseUrl={}, path={}, model={}, durationMs={}",
                    provider.configValue(),
                    baseUrl,
                    path,
                    model,
                    durationMs(startedAt)
            );
            return response;
        } catch (RestClientResponseException exception) {
            OpenAiError error = openAiError(exception);
            LOGGER.warn(
                    "OpenAI request failed: provider={}, baseUrl={}, path={}, model={}, status={}, errorCode={}, errorMessage={}, requestId={}, durationMs={}",
                    provider.configValue(),
                    baseUrl,
                    path,
                    model,
                    exception.getStatusCode().value(),
                    error.code(),
                    error.message(),
                    error.requestId(),
                    durationMs(startedAt)
            );
            throw new OpenAiException(
                    "调用 OpenAI 失败：provider=%s path=%s status=%d code=%s message=%s".formatted(
                            provider.configValue(),
                            path,
                            exception.getStatusCode().value(),
                            error.code(),
                            error.message()
                    ),
                    exception
            );
        } catch (RestClientException exception) {
            LOGGER.warn(
                    "OpenAI request failed: provider={}, baseUrl={}, path={}, model={}, reason={}, durationMs={}",
                    provider.configValue(),
                    baseUrl,
                    path,
                    model,
                    truncate(exception.getMessage()),
                    durationMs(startedAt)
            );
            throw new OpenAiException(
                    "调用 OpenAI 失败：provider=%s path=%s message=%s".formatted(
                            provider.configValue(),
                            path,
                            truncate(exception.getMessage())
                    ),
                    exception
            );
        }
    }

    private RestClient client(AiProvider provider, String baseUrl) {
        String apiKey = configService.get(apiKeyConfigKey(provider))
                .filter(value -> !value.isBlank())
                .orElseThrow(() -> missingApiKey(provider));
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(Duration.ofSeconds(configLong("openai.connectTimeoutSeconds", 30)));
        requestFactory.setReadTimeout(Duration.ofSeconds(configLong("openai.readTimeoutSeconds", 300)));
        RestClient.Builder builder = restClientBuilder.clone()
                .baseUrl(baseUrl)
                .defaultHeader(HttpHeaders.AUTHORIZATION, "Bearer " + apiKey)
                .requestFactory(requestFactory);
        extraHeaders(provider).forEach(builder::defaultHeader);
        return builder.build();
    }

    private AiProvider provider() {
        String provider = config("openai.provider", PROVIDER_OFFICIAL).trim();
        if (provider.equalsIgnoreCase(PROVIDER_THIRD_PARTY)
                || provider.equalsIgnoreCase("third-party")
                || provider.equalsIgnoreCase("third_party")
                || provider.equalsIgnoreCase("custom")
                || provider.equalsIgnoreCase("proxy")
                || provider.equalsIgnoreCase("tokenfree")) {
            return AiProvider.THIRD_PARTY;
        }
        return AiProvider.OFFICIAL;
    }

    private String baseUrl(AiProvider provider) {
        if (provider == AiProvider.THIRD_PARTY) {
            return config("openai.thirdParty.baseUrl", DEFAULT_THIRD_PARTY_BASE_URL);
        }
        return config("openai.baseUrl", DEFAULT_BASE_URL);
    }

    private String apiKeyConfigKey(AiProvider provider) {
        if (provider == AiProvider.THIRD_PARTY) {
            return "openai.thirdParty.apiKey";
        }
        return "openai.apiKey";
    }

    private OpenAiException missingApiKey(AiProvider provider) {
        if (provider == AiProvider.THIRD_PARTY) {
            return new OpenAiException("缺少第三方 OpenAI API Key，请在系统配置中设置 openai.thirdParty.apiKey");
        }
        return new OpenAiException("缺少 OpenAI API Key，请在系统配置中设置 openai.apiKey");
    }

    private String textModel(AiProvider provider) {
        return configForProvider(provider, "openai.textModel", "openai.thirdParty.textModel", DEFAULT_TEXT_MODEL);
    }

    private String imageModel(AiProvider provider) {
        return configForProvider(provider, "openai.imageModel", "openai.thirdParty.imageModel", DEFAULT_IMAGE_MODEL);
    }

    private String imageQuality(AiProvider provider) {
        return configForProvider(provider, "openai.imageQuality", "openai.thirdParty.imageQuality", DEFAULT_IMAGE_QUALITY);
    }

    private String imageOutputFormat(AiProvider provider) {
        return configForProvider(provider, "openai.imageOutputFormat", "openai.thirdParty.imageOutputFormat", DEFAULT_IMAGE_FORMAT);
    }

    private String configForProvider(String officialKey, String thirdPartyKey, String defaultValue) {
        return configForProvider(provider(), officialKey, thirdPartyKey, defaultValue);
    }

    private String configForProvider(AiProvider provider, String officialKey, String thirdPartyKey, String defaultValue) {
        if (provider == AiProvider.THIRD_PARTY) {
            return config(thirdPartyKey, defaultValue);
        }
        return config(officialKey, defaultValue);
    }

    private String config(String key, String defaultValue) {
        return configService.get(key).filter(value -> !value.isBlank()).orElse(defaultValue);
    }

    private long configLong(String key, long defaultValue) {
        return configService.get(key)
                .filter(value -> !value.isBlank())
                .map(value -> {
                    try {
                        return Long.parseLong(value.trim());
                    } catch (NumberFormatException exception) {
                        return defaultValue;
                    }
                })
                .orElse(defaultValue);
    }

    private boolean configBoolean(String key, boolean defaultValue) {
        return configService.get(key)
                .filter(value -> !value.isBlank())
                .map(value -> {
                    String normalized = value.trim();
                    if (normalized.equalsIgnoreCase("true")
                            || normalized.equalsIgnoreCase("yes")
                            || normalized.equals("1")) {
                        return true;
                    }
                    if (normalized.equalsIgnoreCase("false")
                            || normalized.equalsIgnoreCase("no")
                            || normalized.equals("0")) {
                        return false;
                    }
                    return defaultValue;
                })
                .orElse(defaultValue);
    }

    private Map<String, String> extraHeaders(AiProvider provider) {
        if (provider != AiProvider.THIRD_PARTY) {
            return Map.of();
        }
        String raw = configService.get("openai.thirdParty.extraHeaders").orElse("");
        if (raw.isBlank()) {
            return Map.of();
        }
        Map<String, String> headers = new LinkedHashMap<>();
        for (String token : raw.split("[\\n;]+")) {
            String line = token.trim();
            if (line.isBlank()) {
                continue;
            }
            int separator = headerSeparator(line);
            if (separator <= 0) {
                continue;
            }
            String name = line.substring(0, separator).trim();
            String value = line.substring(separator + 1).trim();
            if (!name.isBlank() && !value.isBlank() && !name.equalsIgnoreCase(HttpHeaders.AUTHORIZATION)) {
                headers.put(name, value);
            }
        }
        return headers;
    }

    private String requestModel(Object body) {
        if (body instanceof Map<?, ?> values) {
            Object model = values.get("model");
            if (model != null) {
                return model.toString();
            }
        }
        return "";
    }

    private OpenAiError openAiError(RestClientResponseException exception) {
        String requestId = firstHeader(exception, "x-request-id", "request-id", "openai-request-id");
        String body = exception.getResponseBodyAsString();
        if (body == null || body.isBlank()) {
            return new OpenAiError("", truncate(exception.getStatusText()), requestId);
        }
        try {
            JsonNode root = OBJECT_MAPPER.readTree(body);
            JsonNode error = root.has("error") && root.path("error").isObject() ? root.path("error") : root;
            return new OpenAiError(
                    firstText(error, "code", "type"),
                    truncate(firstText(error, "message", "error")),
                    requestId
            );
        } catch (Exception parseException) {
            return new OpenAiError("", truncate(body), requestId);
        }
    }

    private String firstHeader(RestClientResponseException exception, String... names) {
        if (exception.getResponseHeaders() == null) {
            return "";
        }
        for (String name : names) {
            String value = exception.getResponseHeaders().getFirst(name);
            if (value != null && !value.isBlank()) {
                return value;
            }
        }
        return "";
    }

    private String firstText(JsonNode node, String... fields) {
        for (String field : fields) {
            String value = node.path(field).asText("");
            if (!value.isBlank()) {
                return value;
            }
        }
        return "";
    }

    private String truncate(String value) {
        if (value == null) {
            return "";
        }
        String normalized = value.replaceAll("\\s+", " ").trim();
        if (normalized.length() <= 500) {
            return normalized;
        }
        return normalized.substring(0, 500);
    }

    private long durationMs(long startedAt) {
        return Duration.ofNanos(System.nanoTime() - startedAt).toMillis();
    }

    private int headerSeparator(String line) {
        int colon = line.indexOf(':');
        int equals = line.indexOf('=');
        if (colon < 0) {
            return equals;
        }
        if (equals < 0) {
            return colon;
        }
        return Math.min(colon, equals);
    }

    private String firstTextFromOutput(JsonNode response) {
        for (JsonNode output : response.path("output")) {
            for (JsonNode content : output.path("content")) {
                List<String> fields = List.of("text", "output_text");
                for (String field : fields) {
                    String value = content.path(field).asText("");
                    if (!value.isBlank()) {
                        return value;
                    }
                }
            }
        }
        return "";
    }

    private enum AiProvider {
        OFFICIAL("official"),
        THIRD_PARTY("thirdParty");

        private final String configValue;

        AiProvider(String configValue) {
            this.configValue = configValue;
        }

        private String configValue() {
            return configValue;
        }
    }

    private record OpenAiError(String code, String message, String requestId) {
    }
}
