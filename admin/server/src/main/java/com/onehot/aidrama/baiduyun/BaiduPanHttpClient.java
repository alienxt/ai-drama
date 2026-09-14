package com.onehot.aidrama.baiduyun;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.onehot.aidrama.configs.SystemConfigService;
import okhttp3.FormBody;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.ResponseBody;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.springframework.web.util.UriComponentsBuilder;

import java.io.IOException;
import java.net.Authenticator;
import java.net.InetSocketAddress;
import java.net.PasswordAuthentication;
import java.net.Proxy;
import java.net.URI;
import java.net.SocketTimeoutException;
import java.net.URLEncoder;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.Function;
import java.util.regex.Matcher;
import java.util.stream.Collectors;

@Component
public class BaiduPanHttpClient implements BaiduPanClient {
    private static final String TOKEN_URL = "https://openapi.baidu.com/oauth/2.0/token";
    private static final String XPAN_FILE_URL = "https://pan.baidu.com/rest/2.0/xpan/file";
    private static final String XPAN_MEDIA_URL = "https://pan.baidu.com/rest/2.0/xpan/multimedia";
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final List<Integer> ACCESS_TOKEN_ERROR_CODES = List.of(-6, 110, 111);

    private final SystemConfigService configService;
    private final String tokenUrl;
    private final String xpanFileUrl;
    private final String xpanMediaUrl;

    @Autowired
    public BaiduPanHttpClient(SystemConfigService configService) {
        this(configService, TOKEN_URL, XPAN_FILE_URL, XPAN_MEDIA_URL);
    }

    BaiduPanHttpClient(
            SystemConfigService configService,
            String tokenUrl,
            String xpanFileUrl,
            String xpanMediaUrl
    ) {
        this.configService = configService;
        this.tokenUrl = tokenUrl;
        this.xpanFileUrl = xpanFileUrl;
        this.xpanMediaUrl = xpanMediaUrl;
    }

    @Override
    public List<BaiduPanEntry> listDirectory(String remotePath) {
        Map<String, Object> payload = getJsonWithAccessTokenRetry(
                accessToken -> listDirectoryUri(xpanFileUrl, remotePath, accessToken)
        );
        Object rawList = payload.getOrDefault("list", List.of());
        return MAPPER.convertValue(rawList, new TypeReference<List<Map<String, Object>>>() {
                }).stream()
                .map(this::entryFrom)
                .toList();
    }

    @Override
    public String createStreamingUrl(String remotePath) {
        return streamingUri(xpanFileUrl, remotePath, ensureAccessToken(false), "M3U8_AUTO_720").toString();
    }

    @Override
    public String createDownloadUrl(String remotePath) {
        return createDownloadUrls(List.of(remotePath)).getFirst();
    }

    @Override
    public List<String> createDownloadUrls(List<String> remotePaths) {
        if (remotePaths.isEmpty()) {
            return List.of();
        }
        Map<String, BaiduPanEntry> entriesByPath = entriesByPath(remotePaths);
        List<Long> fsIds = remotePaths.stream()
                .map(path -> entriesByPath.get(path))
                .map(BaiduPanEntry::fsId)
                .toList();
        Map<String, Object> payload = getJsonWithAccessTokenRetry(
                accessToken -> encodedUri(xpanMediaUrl, Map.of(
                        "method", "filemetas",
                        "access_token", accessToken,
                        "fsids", MAPPER.valueToTree(fsIds).toString(),
                        "dlink", "1"
                ))
        );
        List<Map<String, Object>> list = MAPPER.convertValue(payload.get("list"), new TypeReference<>() {
        });
        Map<Long, String> dlinksByFsId = new HashMap<>();
        if (list != null) {
            for (Map<String, Object> item : list) {
                if (item.get("fs_id") != null && item.get("dlink") != null) {
                    dlinksByFsId.put(((Number) item.get("fs_id")).longValue(), String.valueOf(item.get("dlink")));
                }
            }
        }
        String token = ensureAccessToken(false);
        List<String> urls = new ArrayList<>();
        for (Long fsId : fsIds) {
            String dlink = dlinksByFsId.get(fsId);
            if (dlink == null) {
                throw new BaiduPanException("Baidu dlink missing for fs_id: " + fsId);
            }
            urls.add(appendAccessToken(dlink, token));
        }
        return urls;
    }

    @Override
    public String readUrl(String url) {
        return withAccessTokenUrlRetry(url, this::readUrlOnce);
    }

    private String readUrlOnce(String url) {
        try (Response response = execute(requestBuilder(URI.create(url)).get().build())) {
            String body = responseBody(response).string();
            if (response.code() >= 400) {
                throw httpResponseException("Baidu URL read", response.code(), body, URI.create(url));
            }
            rejectBaiduErrorBody(body, "Baidu URL read failed");
            return body;
        } catch (IOException exception) {
            throw new BaiduPanException("Baidu URL read failed", exception);
        }
    }

    @Override
    public byte[] downloadUrl(String url) {
        return withAccessTokenUrlRetry(url, this::downloadUrlOnce);
    }

    private byte[] downloadUrlOnce(String url) {
        try (Response response = execute(requestBuilder(URI.create(url)).get().build())) {
            byte[] body = responseBody(response).bytes();
            String contentType = response.header("Content-Type", "");
            if (response.code() >= 400) {
                throw httpResponseException("Baidu URL download", response.code(), textBody(body, contentType), URI.create(url));
            }
            if (contentType.contains("application/json") || contentType.contains("text/")) {
                rejectBaiduErrorBody(new String(body, StandardCharsets.UTF_8), "Baidu URL download failed");
            }
            return body;
        } catch (IOException exception) {
            throw new BaiduPanException("Baidu URL download failed", exception);
        }
    }

    @Override
    public String readTextFile(String remotePath) {
        return readUrl(createDownloadUrl(remotePath));
    }

    @Override
    public void downloadFile(String remotePath, Path target) {
        downloadFileFromUrl(createDownloadUrl(remotePath), target);
    }

    private void downloadFileFromUrl(String url, Path target) {
        withAccessTokenUrlRetry(url, retryUrl -> {
            downloadFileOnce(retryUrl, target);
            return null;
        });
    }

    private void downloadFileOnce(String url, Path target) {
        try {
            Files.createDirectories(target.getParent());
            Path temp = target.resolveSibling(target.getFileName() + ".tmp");
            try (Response response = execute(requestBuilder(URI.create(url)).get().build())) {
                byte[] bytes = responseBody(response).bytes();
                String contentType = response.header("Content-Type", "");
                if (response.code() >= 400) {
                    Files.deleteIfExists(temp);
                    throw httpResponseException("Baidu file download", response.code(), textBody(bytes, contentType), URI.create(url));
                }
                Files.write(temp, bytes);
                if (contentType.contains("application/json") || contentType.contains("text/")) {
                    String text = Files.readString(temp, StandardCharsets.UTF_8);
                    rejectBaiduErrorBody(text, "Baidu file download failed");
                }
                Files.move(temp, target, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
            }
        } catch (IOException exception) {
            throw new BaiduPanException("Baidu file download failed", exception);
        }
    }

    private Map<String, BaiduPanEntry> entriesByPath(List<String> remotePaths) {
        Map<String, List<String>> pathsByParent = remotePaths.stream()
                .collect(Collectors.groupingBy(this::parentPath));
        Map<String, BaiduPanEntry> entriesByPath = new HashMap<>();
        for (Map.Entry<String, List<String>> group : pathsByParent.entrySet()) {
            Map<String, BaiduPanEntry> available = listDirectory(group.getKey()).stream()
                    .collect(Collectors.toMap(BaiduPanEntry::path, entry -> entry));
            for (String path : group.getValue()) {
                BaiduPanEntry entry = available.get(path);
                if (entry == null || entry.fsId() == null) {
                    throw new BaiduPanException("Baidu path not found: " + path);
                }
                entriesByPath.put(path, entry);
            }
        }
        return entriesByPath;
    }

    private String parentPath(String remotePath) {
        int slash = remotePath.lastIndexOf('/');
        return slash <= 0 ? "/" : remotePath.substring(0, slash);
    }

    private String ensureAccessToken(boolean forceRefresh) {
        String accessToken = configService.get("baidu.accessToken").orElse("");
        if (forceRefresh || tokenExpired()) {
            try {
                refreshAccessToken();
            } catch (BaiduPanException exception) {
                if (!forceRefresh && !accessToken.isBlank() && accessTokenIsUsable(accessToken)) {
                    return accessToken;
                }
                throw exception;
            }
        }
        return requireConfig("baidu.accessToken");
    }

    private boolean tokenExpired() {
        long obtainedAt = configLong("baidu.tokenObtainedAt", 0L);
        long expiresIn = configLong("baidu.expiresIn", 0L);
        return Instant.now().getEpochSecond() >= obtainedAt + Math.max(expiresIn - 60, 0);
    }

    private void refreshAccessToken() {
        Map<String, Object> payload;
        try {
            String body = form(Map.of(
                    "grant_type", "refresh_token",
                    "refresh_token", requireConfig("baidu.refreshToken"),
                    "client_id", requireConfig("baidu.clientId"),
                    "client_secret", requireConfig("baidu.clientSecret")
            ));
            payload = postForm(URI.create(tokenUrl), body);
        } catch (BaiduPanException exception) {
            throw new BaiduPanException("Baidu token refresh failed: " + exception.getMessage(), exception);
        }
        if (payload.get("access_token") == null) {
            throw new BaiduPanException("Baidu token refresh failed" + baiduOauthMessage(payload));
        }
        configService.put("baidu.accessToken", String.valueOf(payload.get("access_token")), true);
        if (payload.get("refresh_token") != null) {
            configService.put("baidu.refreshToken", String.valueOf(payload.get("refresh_token")), true);
        }
        configService.put("baidu.expiresIn", String.valueOf(payload.getOrDefault("expires_in", "0")), false);
        configService.put("baidu.tokenObtainedAt", String.valueOf(Instant.now().getEpochSecond()), false);
    }

    private String requireConfig(String key) {
        try {
            return configService.require(key);
        } catch (RuntimeException exception) {
            throw new BaiduPanException("Baidu config missing: " + key, exception);
        }
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

    private boolean accessTokenIsUsable(String accessToken) {
        try {
            getJson(listDirectoryUri(xpanFileUrl, "/", accessToken));
            return true;
        } catch (BaiduPanException exception) {
            return false;
        }
    }

    private Map<String, Object> getJson(URI uri) {
        return sendJson(requestBuilder(uri).get().build());
    }

    private Map<String, Object> getJsonWithAccessTokenRetry(Function<String, URI> uriFactory) {
        String accessToken = ensureAccessToken(false);
        try {
            return getJson(uriFactory.apply(accessToken));
        } catch (BaiduApiResponseException exception) {
            if (!accessTokenError(exception)) {
                throw exception;
            }
            String refreshedToken = ensureAccessToken(true);
            return getJson(uriFactory.apply(refreshedToken));
        }
    }

    private <T> T withAccessTokenUrlRetry(String url, Function<String, T> action) {
        try {
            return action.apply(url);
        } catch (BaiduApiResponseException exception) {
            if (!accessTokenError(exception) || !containsAccessToken(url)) {
                throw exception;
            }
            String refreshedToken = ensureAccessToken(true);
            return action.apply(replaceAccessToken(url, refreshedToken));
        }
    }

    private Map<String, Object> postForm(URI uri, String body) {
        FormBody.Builder form = new FormBody.Builder(StandardCharsets.UTF_8);
        for (String pair : body.split("&")) {
            int equals = pair.indexOf('=');
            if (equals > 0) {
                form.addEncoded(pair.substring(0, equals), pair.substring(equals + 1));
            }
        }
        Request request = requestBuilder(uri)
                .post(form.build())
                .build();
        return sendJson(request);
    }

    private Map<String, Object> sendJson(Request request) {
        try (Response response = execute(request)) {
            String body = responseBody(response).string();
            if (response.code() >= 400) {
                Map<String, Object> payload = jsonObjectOrEmpty(body);
                throw new BaiduApiResponseException(
                        "Baidu HTTP " + response.code() + baiduOauthMessage(payload)
                                + baiduMessage(payload) + " for " + safeUri(request.url().uri()),
                        response.code(),
                        payload
                );
            }
            Map<String, Object> payload = parseJsonBody(body);
            Optional<Integer> errno = numericValue(payload.get("errno"));
            if (errno.isPresent() && errno.get() != 0) {
                throw new BaiduApiResponseException(
                        "Baidu API error " + errno.get() + baiduMessage(payload)
                                + " for " + safeUri(request.url().uri()),
                        response.code(),
                        payload
                );
            }
            Optional<Integer> errorCode = numericValue(payload.get("error_code"));
            if (errorCode.isPresent() && errorCode.get() != 0) {
                throw new BaiduApiResponseException(
                        "Baidu API error " + errorCode.get() + baiduMessage(payload)
                                + " for " + safeUri(request.url().uri()),
                        response.code(),
                        payload
                );
            }
            return payload;
        } catch (IOException exception) {
            if (exception instanceof SocketTimeoutException) {
                throw new BaiduPanException("Baidu request timed out for " + safeUri(request.url().uri()), exception);
            }
            throw new BaiduPanException("Baidu response parse failed", exception);
        }
    }

    private Map<String, Object> parseJsonBody(String body) throws IOException {
        return MAPPER.readValue(body, new TypeReference<>() {
        });
    }

    private BaiduApiResponseException httpResponseException(String message, int httpStatus, String body, URI uri) {
        Map<String, Object> payload = jsonObjectOrEmpty(body);
        return new BaiduApiResponseException(
                message + " HTTP " + httpStatus + baiduOauthMessage(payload)
                        + baiduMessage(payload) + " for " + safeUri(uri),
                httpStatus,
                payload
        );
    }

    private Response execute(Request request) throws IOException {
        return httpClient().newCall(request).execute();
    }

    private ResponseBody responseBody(Response response) {
        ResponseBody body = response.body();
        if (body == null) {
            throw new BaiduPanException("Baidu response body is empty");
        }
        return body;
    }

    private Request.Builder requestBuilder(URI uri) {
        return new Request.Builder()
                .url(uri.toString())
                .header("User-Agent", "pan.baidu.com")
                .header("Referer", "https://pan.baidu.com/");
    }

    private OkHttpClient httpClient() {
        OkHttpClient.Builder builder = new OkHttpClient.Builder()
                .followRedirects(true)
                .connectTimeout(Duration.ofSeconds(30))
                .readTimeout(Duration.ofSeconds(30))
                .writeTimeout(Duration.ofSeconds(30));
        resolveProxySettings(configService::get).ifPresent(settings -> {
            builder.proxy(new Proxy(
                    Proxy.Type.SOCKS,
                    new InetSocketAddress(settings.host(), settings.port())
            ));
            configureSocksAuthentication(settings);
        });
        return builder.build();
    }

    private void configureSocksAuthentication(ProxySettings settings) {
        if (settings.username().isBlank() || settings.password().isBlank()) {
            return;
        }
        Authenticator.setDefault(new Authenticator() {
            @Override
            protected PasswordAuthentication getPasswordAuthentication() {
                return new PasswordAuthentication(settings.username(), settings.password().toCharArray());
            }
        });
    }

    private BaiduPanEntry entryFrom(Map<String, Object> item) {
        return new BaiduPanEntry(
                String.valueOf(item.get("path")),
                String.valueOf(item.get("server_filename")),
                ((Number) item.getOrDefault("isdir", 0)).intValue() == 1,
                item.get("fs_id") == null ? null : ((Number) item.get("fs_id")).longValue(),
                item.get("size") == null ? 0 : ((Number) item.get("size")).longValue()
        );
    }

    private String form(Map<String, String> values) {
        return values.entrySet().stream()
                .map(entry -> encode(entry.getKey()) + "=" + encode(entry.getValue()))
                .reduce((left, right) -> left + "&" + right)
                .orElse("");
    }

    private String encode(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }

    static URI listDirectoryUri(String remotePath, String accessToken) {
        return listDirectoryUri(XPAN_FILE_URL, remotePath, accessToken);
    }

    private static URI listDirectoryUri(String xpanFileUrl, String remotePath, String accessToken) {
        return encodedUri(xpanFileUrl, Map.of(
                "method", "list",
                "access_token", accessToken,
                "dir", remotePath
        ));
    }

    static URI streamingUri(String remotePath, String accessToken, String type) {
        return streamingUri(XPAN_FILE_URL, remotePath, accessToken, type);
    }

    private static URI streamingUri(String xpanFileUrl, String remotePath, String accessToken, String type) {
        return encodedUri(xpanFileUrl, Map.of(
                "method", "streaming",
                "access_token", accessToken,
                "path", remotePath,
                "type", type
        ));
    }

    private static URI encodedUri(String url, Map<String, String> queryParams) {
        UriComponentsBuilder builder = UriComponentsBuilder.fromHttpUrl(url);
        queryParams.forEach(builder::queryParam);
        return builder.encode().build().toUri();
    }

    static String safeUri(URI uri) {
        return uri.toString()
                .replaceAll("(?i)(access_token=)[^&]+", "$1***")
                .replaceAll("(?i)(refresh_token=)[^&]+", "$1***")
                .replaceAll("(?i)(client_secret=)[^&]+", "$1***");
    }

    private String baiduMessage(Map<String, Object> payload) {
        Object message = Optional.ofNullable(payload.get("errmsg"))
                .orElseGet(() -> Optional.ofNullable(payload.get("error_msg")).orElse(payload.get("show_msg")));
        if (message == null || String.valueOf(message).isBlank()) {
            return "";
        }
        return " (" + message + ")";
    }

    private String baiduOauthMessage(Map<String, Object> payload) {
        if (payload == null || payload.isEmpty()) {
            return "";
        }
        Object error = payload.get("error");
        Object description = payload.get("error_description");
        if ((error == null || String.valueOf(error).isBlank())
                && (description == null || String.valueOf(description).isBlank())) {
            return "";
        }
        if (description == null || String.valueOf(description).isBlank()) {
            return " (" + error + ")";
        }
        if (error == null || String.valueOf(error).isBlank()) {
            return " (" + description + ")";
        }
        return " (" + error + ": " + description + ")";
    }

    static Optional<ProxySettings> resolveProxySettings(Function<String, Optional<String>> config) {
        boolean enabled = config.apply("baidu.proxyEnabled").map(Boolean::parseBoolean).orElse(false);
        if (!enabled) {
            return Optional.empty();
        }
        String host = config.apply("baidu.proxyHost").orElse("").trim();
        int port = config.apply("baidu.proxyPort").map(BaiduPanHttpClient::parsePort).orElse(0);
        if (host.isBlank() || port <= 0) {
            return Optional.empty();
        }
        String username = config.apply("baidu.proxyUsername").orElse("").trim();
        String password = config.apply("baidu.proxyPassword").orElse("");
        return Optional.of(new ProxySettings(host, port, username, password));
    }

    private static int parsePort(String value) {
        try {
            return Integer.parseInt(value.trim());
        } catch (NumberFormatException exception) {
            return 0;
        }
    }

    record ProxySettings(String host, int port, String username, String password) {
    }

    private String appendAccessToken(String url, String accessToken) {
        return url + (url.contains("?") ? "&" : "?") + "access_token=" + encode(accessToken);
    }

    private void rejectBaiduErrorBody(String body, String message) {
        String trimmed = body == null ? "" : body.trim();
        if (!trimmed.startsWith("{")) {
            return;
        }
        try {
            Map<String, Object> payload = MAPPER.readValue(trimmed, new TypeReference<>() {
            });
            Optional<Integer> errorCode = numericValue(payload.get("error_code"));
            Optional<Integer> errno = numericValue(payload.get("errno"));
            boolean hasNonNumericErrorCode = payload.get("error_code") != null && errorCode.isEmpty();
            if (hasNonNumericErrorCode
                    || errorCode.filter(code -> code != 0).isPresent()
                    || errno.filter(code -> code != 0).isPresent()) {
                throw new BaiduApiResponseException(
                        message + baiduOauthMessage(payload) + baiduMessage(payload),
                        200,
                        payload
                );
            }
        } catch (IOException ignored) {
            // A normal intro may be JSON-like text; only reject bodies we can parse as Baidu errors.
        }
    }

    private boolean accessTokenError(BaiduApiResponseException exception) {
        if (exception.httpStatus() == 401) {
            return true;
        }
        Map<String, Object> payload = exception.payload();
        Optional<Integer> errno = numericValue(payload.get("errno"));
        if (errno.filter(ACCESS_TOKEN_ERROR_CODES::contains).isPresent()) {
            return true;
        }
        Optional<Integer> errorCode = numericValue(payload.get("error_code"));
        if (errorCode.filter(ACCESS_TOKEN_ERROR_CODES::contains).isPresent()) {
            return true;
        }
        String message = (payload + " " + exception.getMessage()).toLowerCase();
        boolean mentionsAccessToken = message.contains("access token") || message.contains("access_token");
        return mentionsAccessToken && (
                message.contains("expired")
                        || message.contains("invalid")
                        || message.contains("no longer valid")
        );
    }

    private Optional<Integer> numericValue(Object value) {
        if (value instanceof Number number) {
            return Optional.of(number.intValue());
        }
        if (value instanceof String string && !string.isBlank()) {
            try {
                return Optional.of(Integer.parseInt(string.trim()));
            } catch (NumberFormatException ignored) {
                return Optional.empty();
            }
        }
        return Optional.empty();
    }

    private Map<String, Object> jsonObjectOrEmpty(String body) {
        String trimmed = body == null ? "" : body.trim();
        if (!trimmed.startsWith("{")) {
            return Map.of();
        }
        try {
            return MAPPER.readValue(trimmed, new TypeReference<>() {
            });
        } catch (IOException exception) {
            return Map.of();
        }
    }

    private String textBody(byte[] bytes, String contentType) {
        if (bytes == null || bytes.length == 0) {
            return "";
        }
        if (contentType.contains("application/json") || contentType.contains("text/")) {
            return new String(bytes, StandardCharsets.UTF_8);
        }
        return "";
    }

    private boolean containsAccessToken(String url) {
        return url.matches("(?i).*([?&]access_token=).*");
    }

    private String replaceAccessToken(String url, String accessToken) {
        return url.replaceFirst("(?i)(access_token=)[^&#]*", "$1" + Matcher.quoteReplacement(encode(accessToken)));
    }

    private static class BaiduApiResponseException extends BaiduPanException {
        private final int httpStatus;
        private final Map<String, Object> payload;

        private BaiduApiResponseException(String message, int httpStatus, Map<String, Object> payload) {
            super(message);
            this.httpStatus = httpStatus;
            this.payload = payload == null ? Map.of() : payload;
        }

        private int httpStatus() {
            return httpStatus;
        }

        private Map<String, Object> payload() {
            return payload;
        }
    }
}
