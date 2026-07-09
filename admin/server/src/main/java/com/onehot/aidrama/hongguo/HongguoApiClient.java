package com.onehot.aidrama.hongguo;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.onehot.aidrama.common.TraceIdFilter;
import com.onehot.aidrama.configs.SystemConfigService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.util.UriComponentsBuilder;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
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
    private static final Logger log = LoggerFactory.getLogger(HongguoApiClient.class);
    private static final ZoneId CHINA_ZONE = ZoneId.of("Asia/Shanghai");
    private static final DateTimeFormatter DATE_FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd");
    private static final DateTimeFormatter DATE_TIME_FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final SystemConfigService configService;
    private final RestClient.Builder restClientBuilder;
    private final HongguoApiDebugLogRepository debugLogRepository;

    public HongguoApiClient(
            SystemConfigService configService,
            RestClient.Builder restClientBuilder,
            HongguoApiDebugLogRepository debugLogRepository
    ) {
        this.configService = configService;
        this.restClientBuilder = restClientBuilder;
        this.debugLogRepository = debugLogRepository;
    }

    public HongguoApiModels.MangaSearchPage searchMangaDramas(String keyword, int page) {
        String effectiveKeyword = keyword == null || keyword.isBlank() ? "漫剧" : keyword.trim();
        int effectivePage = Math.max(page, 1);
        JsonNode data = get("/hg_new", Map.of(
                "type", "mj_search",
                "keyword", effectiveKeyword,
                "page", String.valueOf(effectivePage)
        ));
        return new HongguoApiModels.MangaSearchPage(effectiveKeyword, effectivePage, parseMangaSearchItems(data));
    }

    public HongguoApiModels.MangaSearchPage fetchNewDramas(int page, Instant since) {
        int effectivePage = Math.max(page, 1);
        JsonNode data = get("/hg_new_play", Map.of(
                "type", "detail",
                "date", formatChinaDate(since),
                "page", String.valueOf(effectivePage)
        ));
        return new HongguoApiModels.MangaSearchPage("红果新剧", effectivePage, parseMangaSearchItems(data));
    }

    public HongguoApiModels.MangaSearchPage fetchScreenedAiMangaNewDramas(int page) {
        return fetchScreenedAiMangaNewDramas(page, null, List.of());
    }

    public HongguoApiModels.MangaSearchPage fetchScreenedAiMangaNewDramas(int page, String sessionId, List<String> filterIds) {
        int effectivePage = Math.max(page, 1);
        Map<String, String> params = new LinkedHashMap<>();
        params.put("type", "list");
        params.put("genre", "ai_series");
        params.put("online_time", "days_7");
        params.put("duration", "duration_60_120");
        if (effectivePage > 1 && sessionId != null && !sessionId.isBlank()) {
            params.put("session_id", sessionId.trim());
        }
        String joinedFilterIds = joinFilterIds(filterIds);
        if (effectivePage > 1 && joinedFilterIds != null) {
            params.put("filter_ids", joinedFilterIds);
        }
        JsonNode data = get("/hg_screening", params);
        List<HongguoApiModels.MangaSearchItem> items = parseMangaSearchItems(data);
        return new HongguoApiModels.MangaSearchPage(
                "AI漫剧7日上新60-120分钟",
                effectivePage,
                items,
                firstText(data, "session_id", "sessionId"),
                providerDramaIds(items)
        );
    }

    static String formatChinaDate(Instant instant) {
        return DATE_FORMATTER.format(LocalDateTime.ofInstant(instant, CHINA_ZONE));
    }

    static String formatChinaDateTime(Instant instant) {
        return DATE_TIME_FORMATTER.format(LocalDateTime.ofInstant(instant, CHINA_ZONE));
    }

    List<HongguoApiModels.MangaSearchItem> parseMangaSearchItems(JsonNode data) {
        List<HongguoApiModels.MangaSearchItem> items = new ArrayList<>();
        for (JsonNode item : records(data, "lists", "list", "items", "records")) {
            items.add(new HongguoApiModels.MangaSearchItem(
                    firstText(item, "id", "book_id", "album_id", "drama_id"),
                    firstText(item, "name", "title", "book_name", "album_name", "video_name"),
                    firstText(item, "desc", "intro", "summary", "description", "abstract", "brief"),
                    firstText(item, "cover", "cover_url", "poster", "thumb", "image"),
                    firstText(item, "duration", "duration_text"),
                    firstText(item, "score", "rate", "rating"),
                    firstText(item, "category", "type", "genre"),
                    firstText(item, "copyright", "source"),
                    firstInteger(item, "episodeNum", "episode_num", "episode_count", "total_episode", "total_episodes", "chapter_num"),
                    firstLong(item, "playNum", "play_num", "followed_num", "follow_count", "hot", "heat"),
                    parseInstant(firstText(item, "create_time", "publish_time", "online_time", "release_time", "update_time")),
                    mergedTexts(textList(item.path("categories")), recTagTexts(item.path("sub_title_list")), tagInfoTexts(item.path("tag_info"))),
                    mergedTexts(recTagTexts(item.path("rec_tags")), tagInfoTexts(item.path("tag_info")))
            ));
        }
        return items;
    }

    public HongguoApiModels.DramaDetail fetchDetail(String providerDramaId, String keyword) {
        JsonNode data = get("/hg_new", Map.of(
                "type", "detail",
                "id", providerDramaId,
                "keyword", keyword == null ? "" : keyword
        ));
        List<HongguoApiModels.DetailEpisode> episodes = new ArrayList<>();
        int sequence = 1;
        for (JsonNode item : records(data, "lists", "list", "items", "records", "episodes", "video_list")) {
            String providerVideoId = firstText(item, "video_id", "id", "item_id", "episode_id");
            if (providerVideoId == null || providerVideoId.isBlank()) {
                continue;
            }
            int episodeNo = firstInteger(item, sequence, "index", "episode_no", "episode", "sort", "seq");
            episodes.add(new HongguoApiModels.DetailEpisode(
                    Math.max(episodeNo, sequence),
                    firstText(item, "title", "name"),
                    providerVideoId,
                    firstInteger(item, "duration_num", "duration_seconds", "duration_sec")
            ));
            sequence++;
        }
        return new HongguoApiModels.DramaDetail(
                providerDramaId,
                firstText(data, "title", "name", "book_name", "album_name"),
                firstText(data, "intro", "desc", "summary", "description", "abstract", "brief"),
                firstText(data, "cover", "cover_url", "poster", "thumb", "image"),
                firstInteger(data, episodes.size(), "episode_num", "episode_count", "total_episode", "total_episodes", "chapter_num"),
                firstInteger(data, "duration_num", "duration_seconds", "duration_sec"),
                firstLong(data, "play_num", "followed_num", "follow_count", "hot", "heat"),
                parseInstant(firstText(data, "create_time", "publish_time", "online_time", "release_time", "update_time")),
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
        for (JsonNode item : records(data, "video_lists", "lists", "list", "items", "records")) {
            String url = firstText(item, "url", "video_url", "play_url");
            String decryptKey = firstText(item, "decrypt_key", "decryptKey", "key");
            if (url == null || url.isBlank() || decryptKey == null || decryptKey.isBlank()) {
                continue;
            }
            variants.add(new HongguoApiModels.VideoVariant(
                    url,
                    decryptKey,
                    firstText(item, "definition", "quality", "resolution"),
                    firstText(item, "duration", "duration_text"),
                    firstText(item, "size", "file_size"),
                    firstInteger(item, "width"),
                    firstInteger(item, "height")
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
        String requestUrl = debugUrl(path, requestParams);
        long startedAt = System.nanoTime();
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
            writeDebugLog("GET", path, requestUrl, null, responseStatus(response), jsonText(response), null, startedAt);
            return successData(response);
        } catch (RestClientResponseException exception) {
            writeDebugLog(
                    "GET",
                    path,
                    requestUrl,
                    null,
                    exception.getStatusCode().value(),
                    exception.getResponseBodyAsString(),
                    exception.getMessage(),
                    startedAt
            );
            throw new HongguoApiException("调用红果接口失败：" + path, exception);
        } catch (RestClientException exception) {
            writeDebugLog("GET", path, requestUrl, null, -1, null, exception.getMessage(), startedAt);
            throw new HongguoApiException("调用红果接口失败：" + path, exception);
        }
    }

    private JsonNode postForm(String path, Map<String, String> params, MultiValueMap<String, String> body) {
        String apiKey = apiKey();
        Map<String, String> requestParams = withKey(params, apiKey);
        String requestUrl = debugUrl(path, requestParams);
        String requestBody = jsonText(body);
        long startedAt = System.nanoTime();
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
            writeDebugLog("POST", path, requestUrl, requestBody, responseStatus(response), jsonText(response), null, startedAt);
            return successData(response);
        } catch (RestClientResponseException exception) {
            writeDebugLog(
                    "POST",
                    path,
                    requestUrl,
                    requestBody,
                    exception.getStatusCode().value(),
                    exception.getResponseBodyAsString(),
                    exception.getMessage(),
                    startedAt
            );
            throw new HongguoApiException("调用红果解密接口失败", exception);
        } catch (RestClientException exception) {
            writeDebugLog("POST", path, requestUrl, requestBody, -1, null, exception.getMessage(), startedAt);
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

    private void writeDebugLog(
            String method,
            String endpoint,
            String requestUrl,
            String requestBody,
            int status,
            String responseBody,
            String errorMessage,
            long startedAt
    ) {
        try {
            HongguoApiDebugLog entry = new HongguoApiDebugLog();
            entry.setTraceId(MDC.get(TraceIdFilter.TRACE_ID));
            entry.setMethod(method);
            entry.setEndpoint(endpoint);
            entry.setRequestUrl(requestUrl);
            entry.setRequestBody(requestBody);
            entry.setStatus(status);
            entry.setResponseBody(responseBody);
            entry.setErrorMessage(errorMessage);
            entry.setDurationMs(Math.max(0, (System.nanoTime() - startedAt) / 1_000_000));
            entry.setCreatedAt(Instant.now());
            debugLogRepository.save(entry);
        } catch (Exception exception) {
            log.warn("failed to write Hongguo API debug log", exception);
        }
    }

    private String debugUrl(String path, Map<String, String> requestParams) {
        UriComponentsBuilder builder = UriComponentsBuilder.fromUriString(config("hongguo.baseUrl", DEFAULT_BASE_URL))
                .path(path);
        maskSensitive(requestParams).forEach(builder::queryParam);
        return builder.build().toUriString();
    }

    private int responseStatus(JsonNode response) {
        if (response == null || response.isMissingNode() || response.isNull()) {
            return -1;
        }
        return response.path("code").asInt(-1);
    }

    private String jsonText(Object value) {
        if (value == null) {
            return null;
        }
        try {
            return MAPPER.writeValueAsString(value);
        } catch (Exception exception) {
            return String.valueOf(value);
        }
    }

    private Map<String, String> maskSensitive(Map<String, String> values) {
        Map<String, String> masked = new LinkedHashMap<>();
        if (values == null) {
            return masked;
        }
        values.forEach((key, value) -> masked.put(key, isSecretKey(key) ? mask(value) : value));
        return masked;
    }

    private boolean isSecretKey(String key) {
        return key != null && ("key".equalsIgnoreCase(key) || key.toLowerCase().contains("sign"));
    }

    private String mask(String value) {
        if (value == null || value.isBlank()) {
            return value;
        }
        String trimmed = value.trim();
        if (trimmed.length() <= 8) {
            return "***";
        }
        return trimmed.substring(0, 4) + "***" + trimmed.substring(trimmed.length() - 4);
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

    private String joinFilterIds(List<String> filterIds) {
        if (filterIds == null || filterIds.isEmpty()) {
            return null;
        }
        List<String> values = filterIds.stream()
                .filter(value -> value != null && !value.isBlank())
                .map(String::trim)
                .distinct()
                .toList();
        return values.isEmpty() ? null : String.join(",", values);
    }

    private List<String> providerDramaIds(List<HongguoApiModels.MangaSearchItem> items) {
        if (items == null || items.isEmpty()) {
            return List.of();
        }
        return items.stream()
                .map(HongguoApiModels.MangaSearchItem::providerDramaId)
                .filter(value -> value != null && !value.isBlank())
                .map(String::trim)
                .distinct()
                .toList();
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

    private Integer firstInteger(JsonNode node, String... fields) {
        return firstInteger(node, null, fields);
    }

    private Integer firstInteger(JsonNode node, Integer defaultValue, String... fields) {
        for (String field : fields) {
            Integer value = intValue(node, field, null);
            if (value != null) {
                return value;
            }
        }
        return defaultValue;
    }

    private Long firstLong(JsonNode node, String... fields) {
        for (String field : fields) {
            Long value = longValue(node, field, null);
            if (value != null) {
                return value;
            }
        }
        return null;
    }

    private List<JsonNode> records(JsonNode data, String... fields) {
        if (data == null || data.isMissingNode() || data.isNull()) {
            return List.of();
        }
        if (data.isArray()) {
            List<JsonNode> values = new ArrayList<>();
            data.forEach(values::add);
            return values;
        }
        for (String field : fields) {
            JsonNode value = data.path(field);
            if (value.isArray()) {
                List<JsonNode> values = new ArrayList<>();
                value.forEach(values::add);
                return values;
            }
        }
        return List.of();
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

    private List<String> tagInfoTexts(JsonNode tagInfo) {
        if (tagInfo == null || tagInfo.isMissingNode() || tagInfo.isNull()) {
            return List.of();
        }
        if (tagInfo.isTextual()) {
            String value = tagInfo.asText(null);
            return value == null || value.isBlank() ? List.of() : List.of(value.trim());
        }
        if (tagInfo.isArray()) {
            return recTagTexts(tagInfo);
        }
        if (!tagInfo.isObject()) {
            return List.of();
        }
        List<String> values = new ArrayList<>();
        tagInfo.fields().forEachRemaining(entry -> {
            JsonNode value = entry.getValue();
            String text = value.isObject() ? firstText(value, "content", "name", "title", "label") : value.asText(null);
            if (text != null && !text.isBlank()) {
                values.add(text.trim());
            }
        });
        return values;
    }

    @SafeVarargs
    private final List<String> mergedTexts(List<String>... groups) {
        List<String> values = new ArrayList<>();
        if (groups == null) {
            return values;
        }
        for (List<String> group : groups) {
            if (group != null) {
                values.addAll(group);
            }
        }
        return values;
    }

    private Instant parseInstant(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        String trimmed = value.trim();
        if (trimmed.matches("\\d+")) {
            try {
                long timestamp = Long.parseLong(trimmed);
                return trimmed.length() > 10 ? Instant.ofEpochMilli(timestamp) : Instant.ofEpochSecond(timestamp);
            } catch (RuntimeException ignored) {
            }
        }
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
