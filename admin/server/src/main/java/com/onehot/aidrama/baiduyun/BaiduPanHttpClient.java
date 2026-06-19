package com.onehot.aidrama.baiduyun;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.onehot.aidrama.configs.SystemConfigService;
import org.springframework.stereotype.Component;
import org.springframework.web.util.UriComponentsBuilder;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
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
import java.util.stream.Collectors;

@Component
public class BaiduPanHttpClient implements BaiduPanClient {
    private static final String TOKEN_URL = "https://openapi.baidu.com/oauth/2.0/token";
    private static final String XPAN_FILE_URL = "https://pan.baidu.com/rest/2.0/xpan/file";
    private static final String XPAN_MEDIA_URL = "https://pan.baidu.com/rest/2.0/xpan/multimedia";
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final HttpClient httpClient = HttpClient.newBuilder()
            .followRedirects(HttpClient.Redirect.NORMAL)
            .build();
    private final SystemConfigService configService;

    public BaiduPanHttpClient(SystemConfigService configService) {
        this.configService = configService;
    }

    @Override
    public List<BaiduPanEntry> listDirectory(String remotePath) {
        Map<String, Object> payload = getJson(
                UriComponentsBuilder.fromHttpUrl(XPAN_FILE_URL)
                        .queryParam("method", "list")
                        .queryParam("access_token", ensureAccessToken(false))
                        .queryParam("dir", remotePath)
                        .build()
                        .toUri()
        );
        Object rawList = payload.getOrDefault("list", List.of());
        return MAPPER.convertValue(rawList, new TypeReference<List<Map<String, Object>>>() {
                }).stream()
                .map(this::entryFrom)
                .toList();
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
                UriComponentsBuilder.fromHttpUrl(XPAN_MEDIA_URL)
                        .queryParam("method", "filemetas")
                        .queryParam("access_token", ensureAccessToken(false))
                        .queryParam("fsids", MAPPER.valueToTree(fsIds).toString())
                        .queryParam("dlink", "1")
                        .build()
                        .toUri()
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
        HttpRequest request = request(URI.create(createDownloadUrl(remotePath))).GET().build();
        try {
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            if (response.statusCode() >= 400) {
                throw new BaiduPanException("Baidu text download HTTP " + response.statusCode());
            }
            rejectBaiduErrorBody(response.body(), "Baidu text download failed");
            return response.body();
        } catch (IOException exception) {
            throw new BaiduPanException("Baidu text download failed", exception);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new BaiduPanException("Baidu text download interrupted", exception);
        }
    }

    @Override
    public void downloadFile(String remotePath, Path target) {
        HttpRequest request = request(URI.create(createDownloadUrl(remotePath))).GET().build();
        try {
            Files.createDirectories(target.getParent());
            Path temp = target.resolveSibling(target.getFileName() + ".tmp");
            HttpResponse<Path> response = httpClient.send(request, HttpResponse.BodyHandlers.ofFile(temp));
            if (response.statusCode() >= 400) {
                Files.deleteIfExists(temp);
                throw new BaiduPanException("Baidu file download HTTP " + response.statusCode());
            }
            String contentType = response.headers().firstValue("Content-Type").orElse("");
            if (contentType.contains("application/json") || contentType.contains("text/")) {
                String body = Files.readString(temp, StandardCharsets.UTF_8);
                rejectBaiduErrorBody(body, "Baidu file download failed");
            }
            Files.move(temp, target, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } catch (IOException exception) {
            throw new BaiduPanException("Baidu file download failed", exception);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new BaiduPanException("Baidu file download interrupted", exception);
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
        HttpRequest request = request(uri).GET().build();
        return sendJson(request);
    }

    private Map<String, Object> postForm(URI uri, String body) {
        HttpRequest request = request(uri)
                .header("Content-Type", "application/x-www-form-urlencoded")
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();
        return sendJson(request);
    }

    private Map<String, Object> sendJson(HttpRequest request) {
        try {
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() >= 400) {
                throw new BaiduPanException("Baidu HTTP " + response.statusCode());
            }
            Map<String, Object> payload = MAPPER.readValue(response.body(), new TypeReference<>() {
            });
            Object errno = payload.get("errno");
            if (errno instanceof Number number && number.intValue() != 0) {
                throw new BaiduPanException("Baidu API error " + errno + " for " + request.uri());
            }
            return payload;
        } catch (IOException exception) {
            throw new BaiduPanException("Baidu response parse failed", exception);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new BaiduPanException("Baidu request interrupted", exception);
        }
    }

    private HttpRequest.Builder request(URI uri) {
        return HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(20))
                .header("User-Agent", "pan.baidu.com")
                .header("Referer", "https://pan.baidu.com/");
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
