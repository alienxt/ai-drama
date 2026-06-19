package com.onehot.aidrama.baiduyun;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.onehot.aidrama.configs.SystemConfigService;
import okhttp3.FormBody;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.ResponseBody;
import org.springframework.stereotype.Component;
import org.springframework.web.util.UriComponentsBuilder;

import java.io.IOException;
import java.net.Authenticator;
import java.net.InetSocketAddress;
import java.net.PasswordAuthentication;
import java.net.Proxy;
import java.net.URI;
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
import java.util.stream.Collectors;

@Component
public class BaiduPanHttpClient implements BaiduPanClient {
    private static final String TOKEN_URL = "https://openapi.baidu.com/oauth/2.0/token";
    private static final String XPAN_FILE_URL = "https://pan.baidu.com/rest/2.0/xpan/file";
    private static final String XPAN_MEDIA_URL = "https://pan.baidu.com/rest/2.0/xpan/multimedia";
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final SystemConfigService configService;

    public BaiduPanHttpClient(SystemConfigService configService) {
        this.configService = configService;
    }

    @Override
    public List<BaiduPanEntry> listDirectory(String remotePath) {
        Map<String, Object> payload = getJson(listDirectoryUri(remotePath, ensureAccessToken(false)));
        Object rawList = payload.getOrDefault("list", List.of());
        return MAPPER.convertValue(rawList, new TypeReference<List<Map<String, Object>>>() {
                }).stream()
                .map(this::entryFrom)
                .toList();
    }

    @Override
    public String createStreamingUrl(String remotePath) {
        return streamingUri(remotePath, ensureAccessToken(false), "M3U8_AUTO_720").toString();
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
        Map<String, Object> payload = getJson(
                encodedUri(XPAN_MEDIA_URL, Map.of(
                        "method", "filemetas",
                        "access_token", ensureAccessToken(false),
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
    public String readTextFile(String remotePath) {
        try {
            try (Response response = execute(requestBuilder(URI.create(createDownloadUrl(remotePath))).get().build())) {
                if (response.code() >= 400) {
                    throw new BaiduPanException("Baidu text download HTTP " + response.code());
                }
                String body = responseBody(response).string();
                rejectBaiduErrorBody(body, "Baidu text download failed");
                return body;
            }
        } catch (IOException exception) {
            throw new BaiduPanException("Baidu text download failed", exception);
        }
    }

    @Override
    public void downloadFile(String remotePath, Path target) {
        try {
            Files.createDirectories(target.getParent());
            Path temp = target.resolveSibling(target.getFileName() + ".tmp");
            try (Response response = execute(requestBuilder(URI.create(createDownloadUrl(remotePath))).get().build())) {
                if (response.code() >= 400) {
                    Files.deleteIfExists(temp);
                    throw new BaiduPanException("Baidu file download HTTP " + response.code());
                }
                ResponseBody body = responseBody(response);
                Files.write(temp, body.bytes());
                String contentType = response.header("Content-Type", "");
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
        if (forceRefresh || tokenExpired()) {
            refreshAccessToken();
        }
        return configService.require("baidu.accessToken");
    }

    private boolean tokenExpired() {
        long obtainedAt = configService.get("baidu.tokenObtainedAt").map(Long::parseLong).orElse(0L);
        long expiresIn = configService.get("baidu.expiresIn").map(Long::parseLong).orElse(0L);
        return Instant.now().getEpochSecond() >= obtainedAt + Math.max(expiresIn - 60, 0);
    }

    private void refreshAccessToken() {
        String body = form(Map.of(
                "grant_type", "refresh_token",
                "refresh_token", configService.require("baidu.refreshToken"),
                "client_id", configService.require("baidu.clientId"),
                "client_secret", configService.require("baidu.clientSecret")
        ));
        Map<String, Object> payload = postForm(URI.create(TOKEN_URL), body);
        if (payload.get("access_token") == null) {
            throw new BaiduPanException("Baidu token refresh failed");
        }
        configService.put("baidu.accessToken", String.valueOf(payload.get("access_token")), true);
        if (payload.get("refresh_token") != null) {
            configService.put("baidu.refreshToken", String.valueOf(payload.get("refresh_token")), true);
        }
        configService.put("baidu.expiresIn", String.valueOf(payload.getOrDefault("expires_in", "0")), false);
        configService.put("baidu.tokenObtainedAt", String.valueOf(Instant.now().getEpochSecond()), false);
    }

    private Map<String, Object> getJson(URI uri) {
        return sendJson(requestBuilder(uri).get().build());
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
            if (response.code() >= 400) {
                throw new BaiduPanException("Baidu HTTP " + response.code());
            }
            Map<String, Object> payload = MAPPER.readValue(responseBody(response).string(), new TypeReference<>() {
            });
            Object errno = payload.get("errno");
            if (errno instanceof Number number && number.intValue() != 0) {
                throw new BaiduPanException("Baidu API error " + errno + baiduMessage(payload) + " for " + safeUri(request.url().uri()));
            }
            return payload;
        } catch (IOException exception) {
            throw new BaiduPanException("Baidu response parse failed", exception);
        }
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
        return encodedUri(XPAN_FILE_URL, Map.of(
                "method", "list",
                "access_token", accessToken,
                "dir", remotePath
        ));
    }

    static URI streamingUri(String remotePath, String accessToken, String type) {
        return encodedUri(XPAN_FILE_URL, Map.of(
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
            Object errorCode = payload.get("error_code");
            Object errno = payload.get("errno");
            if (errorCode != null || (errno instanceof Number number && number.intValue() != 0)) {
                throw new BaiduPanException(message + ": " + trimmed);
            }
        } catch (IOException ignored) {
            // A normal intro may be JSON-like text; only reject bodies we can parse as Baidu errors.
        }
    }
}
