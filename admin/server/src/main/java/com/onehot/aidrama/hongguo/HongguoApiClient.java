package com.onehot.aidrama.hongguo;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.onehot.aidrama.configs.SystemConfigService;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class HongguoApiClient {
    public static final String DEFAULT_BASE_URL = "https://www.52api.cn/api";
    private static final ZoneId CHINA_ZONE = ZoneId.of("Asia/Shanghai");
    private static final DateTimeFormatter DATE_TIME_FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final SystemConfigService configService;
    private final RestClient.Builder restClientBuilder;

    public HongguoApiClient(SystemConfigService configService, RestClient.Builder restClientBuilder) {
        this.configService = configService;
        this.restClientBuilder = restClientBuilder;
    }

    public HongguoApiModels.CalendarPage fetchCalendar(LocalDate date, int page) {
        LocalDate effectiveDate = date == null ? LocalDate.now(CHINA_ZONE) : date;
        int effectivePage = Math.max(page, 1);
        JsonNode data = get("/hg_new_play", Map.of(
                "type", "detail",
                "date", effectiveDate.toString(),
                "page", String.valueOf(effectivePage)
        ));
        List<HongguoApiModels.CalendarItem> items = new ArrayList<>();
        for (JsonNode item : data.path("lists")) {
            items.add(new HongguoApiModels.CalendarItem(
                    text(item, "id"),
                    firstText(item, "name", "title"),
                    text(item, "desc"),
                    text(item, "cover"),
                    text(item, "duration"),
                    text(item, "score"),
                    text(item, "category"),
                    text(item, "copyright"),
                    intValue(item, "episode_num", null),
                    longValue(item, "play_num", null),
                    parseInstant(text(item, "publish_time")),
                    textList(item.path("categories")),
                    recTagTexts(item.path("rec_tags"))
            ));
        }
        return new HongguoApiModels.CalendarPage(effectiveDate, effectivePage, items);
    }

    public HongguoApiModels.DramaDetail fetchDetail(String providerDramaId, String keyword) {
        JsonNode data = get("/hg_new", Map.of(
                "type", "detail",
                "id", providerDramaId,
                "keyword", keyword == null ? "" : keyword
        ));
        List<HongguoApiModels.DetailEpisode> episodes = new ArrayList<>();
        int sequence = 1;
        for (JsonNode item : data.path("lists")) {
            String providerVideoId = text(item, "video_id");
            if (providerVideoId == null || providerVideoId.isBlank()) {
                continue;
            }
            int episodeNo = intValue(item, "index", sequence);
            episodes.add(new HongguoApiModels.DetailEpisode(
                    Math.max(episodeNo, sequence),
                    text(item, "title"),
                    providerVideoId,
                    intValue(item, "duration_num", null)
            ));
            sequence++;
        }
        return new HongguoApiModels.DramaDetail(
                providerDramaId,
                text(data, "title"),
                text(data, "intro"),
                text(data, "cover"),
                intValue(data, "episode_num", episodes.size()),
                intValue(data, "duration_num", null),
                longValue(data, "play_num", null),
                parseInstant(text(data, "create_time")),
                episodes
        );
    }

    public List<HongguoApiModels.VideoVariant> fetchVideoVariants(String providerDramaId, String keyword, String providerVideoId) {
        JsonNode data = get("/hg_new", Map.of(
                "type", "video",
                "id", providerDramaId,
                "video_id", providerVideoId,
                "keyword", keyword == null ? "" : keyword
        ));
        List<HongguoApiModels.VideoVariant> variants = new ArrayList<>();
        for (JsonNode item : data.path("video_lists")) {
            String url = text(item, "url");
            String decryptKey = text(item, "decrypt_key");
            if (url == null || url.isBlank() || decryptKey == null || decryptKey.isBlank()) {
                continue;
            }
            variants.add(new HongguoApiModels.VideoVariant(
                    url,
                    decryptKey,
                    text(item, "definition"),
                    text(item, "duration"),
                    text(item, "size"),
                    intValue(item, "width", null),
                    intValue(item, "height", null)
            ));
        }
        variants.sort(Comparator.comparingInt(HongguoApiClient::videoPixels).reversed());
        return variants;
    }

    public HongguoApiModels.DecryptedUrl decrypt(String encryptedUrl, String decryptKey) {
        String encodedUrl = Base64.getEncoder().encodeToString(encryptedUrl.getBytes(StandardCharsets.UTF_8));
        MultiValueMap<String, String> body = new LinkedMultiValueMap<>();
        body.add("url", encodedUrl);
        body.add("decrypt_key", decryptKey);
        JsonNode data = postForm("/hg_decrypt", Map.of(), body);
        String url = text(data, "url");
        if (url == null || url.isBlank()) {
            throw new HongguoApiException("红果解密接口未返回下载地址");
        }
        return new HongguoApiModels.DecryptedUrl(url, parseInstant(text(data, "expires")));
    }

    private JsonNode get(String path, Map<String, String> params) {
        String apiKey = apiKey();
        Map<String, String> requestParams = withKey(params, apiKey);
        try {
            JsonNode response = client()
                    .get()
                    .uri(builder -> {
                        var uriBuilder = builder.path(path);
                        requestParams.forEach((key, value) -> uriBuilder.queryParam(key, value));
                        return uriBuilder.build();
                    })
                    .headers(headers -> signHeaders(headers, apiKey))
                    .retrieve()
                    .body(JsonNode.class);
            return successData(response);
        } catch (RestClientException exception) {
            throw new HongguoApiException("调用红果接口失败：" + path, exception);
        }
    }

    private JsonNode postForm(String path, Map<String, String> params, MultiValueMap<String, String> body) {
        String apiKey = apiKey();
        Map<String, String> requestParams = withKey(params, apiKey);
        try {
            JsonNode response = client()
                    .post()
                    .uri(builder -> {
                        var uriBuilder = builder.path(path);
                        requestParams.forEach((key, value) -> uriBuilder.queryParam(key, value));
                        return uriBuilder.build();
                    })
                    .headers(headers -> signHeaders(headers, apiKey))
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .body(body)
                    .retrieve()
                    .body(JsonNode.class);
            return successData(response);
        } catch (RestClientException exception) {
            throw new HongguoApiException("调用红果解密接口失败", exception);
        }
    }

    private RestClient client() {
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(Duration.ofSeconds(configLong("hongguo.connectTimeoutSeconds", 30)));
        requestFactory.setReadTimeout(Duration.ofSeconds(configLong("hongguo.readTimeoutSeconds", 120)));
        return restClientBuilder
                .baseUrl(config("hongguo.baseUrl", DEFAULT_BASE_URL))
                .requestFactory(requestFactory)
                .build();
    }

    private JsonNode successData(JsonNode response) {
        if (response == null || response.isMissingNode() || response.isNull()) {
            throw new HongguoApiException("红果接口无响应");
        }
        int code = response.path("code").asInt(-1);
        if (code != 200) {
            throw new HongguoApiException("红果接口返回失败：" + response.path("msg").asText("code=" + code));
        }
        JsonNode data = response.path("data");
        if (data.isTextual()) {
            String text = data.asText();
            if (text.isBlank()) {
                return data;
            }
            try {
                return MAPPER.readTree(text);
            } catch (Exception ignored) {
                return data;
            }
        }
        return data;
    }

    private Map<String, String> withKey(Map<String, String> params, String apiKey) {
        Map<String, String> values = new LinkedHashMap<>();
        values.put("key", apiKey);
        if (params != null) {
            params.forEach((key, value) -> {
                if (value != null) {
                    values.put(key, value);
                }
            });
        }
        return values;
    }

    private void signHeaders(HttpHeaders headers, String apiKey) {
        long timestamp = Instant.now().getEpochSecond();
        headers.set("X-Api-Key", apiKey);
        headers.set("X-Api-Timestamp", String.valueOf(timestamp));
        headers.set("X-Api-Sign", sign(apiKey, timestamp));
    }

    private String sign(String apiKey, long timestamp) {
        String secretKey = configService.get("hongguo.secretKey")
                .filter(value -> !value.isBlank())
                .orElseThrow(() -> new HongguoApiException("缺少红果 Secret Key，请在系统配置中设置 hongguo.secretKey"));
        String signString = "key=%s&timestamp=%d".formatted(apiKey, timestamp);
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secretKey.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            return HexFormat.of().formatHex(mac.doFinal(signString.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception exception) {
            throw new HongguoApiException("红果签名生成失败", exception);
        }
    }

    private String apiKey() {
        return configService.get("hongguo.apiKey")
                .filter(value -> !value.isBlank())
                .orElseThrow(() -> new HongguoApiException("缺少红果 API Key，请在系统配置中设置 hongguo.apiKey"));
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

    private static int videoPixels(HongguoApiModels.VideoVariant variant) {
        return Math.max(variant.width() == null ? 0 : variant.width(), 0)
                * Math.max(variant.height() == null ? 0 : variant.height(), 0);
    }

    private String firstText(JsonNode node, String... fields) {
        for (String field : fields) {
            String value = text(node, field);
            if (value != null && !value.isBlank()) {
                return value;
            }
        }
        return null;
    }

    private String text(JsonNode node, String field) {
        JsonNode value = node.path(field);
        if (value.isMissingNode() || value.isNull()) {
            return null;
        }
        String text = value.asText(null);
        return text == null || text.isBlank() ? null : text.trim();
    }

    private Integer intValue(JsonNode node, String field, Integer defaultValue) {
        JsonNode value = node.path(field);
        if (value.isNumber()) {
            return value.asInt();
        }
        if (value.isTextual() && !value.asText().isBlank()) {
            try {
                return Integer.parseInt(value.asText().trim());
            } catch (NumberFormatException ignored) {
                return defaultValue;
            }
        }
        return defaultValue;
    }

    private Long longValue(JsonNode node, String field, Long defaultValue) {
        JsonNode value = node.path(field);
        if (value.isNumber()) {
            return value.asLong();
        }
        if (value.isTextual() && !value.asText().isBlank()) {
            try {
                return Long.parseLong(value.asText().trim());
            } catch (NumberFormatException ignored) {
                return defaultValue;
            }
        }
        return defaultValue;
    }

    private List<String> textList(JsonNode array) {
        if (!array.isArray()) {
            return List.of();
        }
        List<String> values = new ArrayList<>();
        for (JsonNode item : array) {
            String value = item.asText(null);
            if (value != null && !value.isBlank()) {
                values.add(value.trim());
            }
        }
        return values;
    }

    private List<String> recTagTexts(JsonNode array) {
        if (!array.isArray()) {
            return List.of();
        }
        List<String> values = new ArrayList<>();
        for (JsonNode item : array) {
            String value = item.isObject() ? text(item, "content") : item.asText(null);
            if (value != null && !value.isBlank()) {
                values.add(value.trim());
            }
        }
        return values;
    }

    private Instant parseInstant(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        String trimmed = value.trim();
        try {
            return Instant.parse(trimmed);
        } catch (RuntimeException ignored) {
        }
        try {
            return LocalDateTime.parse(trimmed, DATE_TIME_FORMATTER).atZone(CHINA_ZONE).toInstant();
        } catch (RuntimeException ignored) {
        }
        return null;
    }
}
