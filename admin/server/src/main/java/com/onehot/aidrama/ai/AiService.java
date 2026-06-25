package com.onehot.aidrama.ai;

import com.fasterxml.jackson.databind.JsonNode;
import com.onehot.aidrama.configs.SystemConfigService;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import java.time.Duration;
import java.util.List;
import java.util.Map;

@Service
public class AiService {
    private static final String DEFAULT_BASE_URL = "https://api.openai.com/v1";
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
        JsonNode response = post(
                "/responses",
                Map.of(
                        "model", config("openai.textModel", DEFAULT_TEXT_MODEL),
                        "instructions", systemPrompt,
                        "input", userPrompt,
                        "text", Map.of("verbosity", "low")
                )
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
        return generateImageBase64(prompt, config("openai.imageSize", DEFAULT_IMAGE_SIZE));
    }

    public String generateImageBase64(String prompt, String size) {
        JsonNode response = post(
                "/images/generations",
                Map.of(
                        "model", config("openai.imageModel", DEFAULT_IMAGE_MODEL),
                        "prompt", prompt,
                        "n", 1,
                        "size", size == null || size.isBlank() ? DEFAULT_IMAGE_SIZE : size,
                        "quality", config("openai.imageQuality", DEFAULT_IMAGE_QUALITY),
                        "output_format", config("openai.imageOutputFormat", DEFAULT_IMAGE_FORMAT)
                )
        );
        String image = response.path("data").path(0).path("b64_json").asText("");
        if (!image.isBlank()) {
            return image;
        }
        throw new OpenAiException("OpenAI 图片模型未返回图片");
    }

    public String textModel() {
        return config("openai.textModel", DEFAULT_TEXT_MODEL);
    }

    public String imageModel() {
        return config("openai.imageModel", DEFAULT_IMAGE_MODEL);
    }

    public String imageSize() {
        return config("openai.imageSize", DEFAULT_IMAGE_SIZE);
    }

    public String videoCoverImageSize() {
        return config("openai.videoCoverImageSize", DEFAULT_VIDEO_COVER_IMAGE_SIZE);
    }

    public String imageQuality() {
        return config("openai.imageQuality", DEFAULT_IMAGE_QUALITY);
    }

    public String imageOutputFormat() {
        return config("openai.imageOutputFormat", DEFAULT_IMAGE_FORMAT);
    }

    private JsonNode post(String path, Object body) {
        try {
            return client()
                    .post()
                    .uri(path)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(body)
                    .retrieve()
                    .body(JsonNode.class);
        } catch (RestClientException exception) {
            throw new OpenAiException("调用 OpenAI 失败", exception);
        }
    }

    private RestClient client() {
        String apiKey = configService.get("openai.apiKey")
                .filter(value -> !value.isBlank())
                .orElseThrow(() -> new OpenAiException("缺少 OpenAI API Key，请在系统配置中设置 openai.apiKey"));
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(Duration.ofSeconds(configLong("openai.connectTimeoutSeconds", 30)));
        requestFactory.setReadTimeout(Duration.ofSeconds(configLong("openai.readTimeoutSeconds", 300)));
        return restClientBuilder
                .baseUrl(config("openai.baseUrl", DEFAULT_BASE_URL))
                .defaultHeader(HttpHeaders.AUTHORIZATION, "Bearer " + apiKey)
                .requestFactory(requestFactory)
                .build();
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
}
