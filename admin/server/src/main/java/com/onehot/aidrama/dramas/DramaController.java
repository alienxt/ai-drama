package com.onehot.aidrama.dramas;

import com.onehot.aidrama.categories.DramaCategoryRepository;
import com.onehot.aidrama.common.ApiResponse;
import com.onehot.aidrama.common.MongoPageQuery;
import com.onehot.aidrama.common.PageResult;
import com.onehot.aidrama.common.TraceIdFilter;
import com.onehot.aidrama.common.error.BusinessException;
import com.onehot.aidrama.common.security.JwtPrincipal;
import com.onehot.aidrama.distribution.DistributionTask;
import com.onehot.aidrama.distribution.DistributionTaskRepository;
import com.onehot.aidrama.distribution.DistributionTaskStatus;
import com.onehot.aidrama.media.MediaAccount;
import com.onehot.aidrama.media.MediaAccountRepository;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.data.mongodb.MongoExpression;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.core.task.TaskExecutor;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.MediaTypeFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.io.IOException;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Date;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;

@RestController
public class DramaController {
    private static final Logger LOGGER = LoggerFactory.getLogger(DramaController.class);

    private final DramaRepository repository;
    private final com.onehot.aidrama.baiduyun.BaiduPanClient baiduPanClient;
    private final MongoTemplate mongoTemplate;
    private final DramaAiService dramaAiService;
    private final DramaCategoryRepository categoryRepository;
    private final MediaAccountRepository mediaAccountRepository;
    private final DistributionTaskRepository distributionTaskRepository;
    private final TaskExecutor taskExecutor;
    private final Path downloadDir;

    @Autowired
    public DramaController(
            DramaRepository repository,
            com.onehot.aidrama.baiduyun.BaiduPanClient baiduPanClient,
            MongoTemplate mongoTemplate,
            DramaAiService dramaAiService,
            DramaCategoryRepository categoryRepository,
            MediaAccountRepository mediaAccountRepository,
            DistributionTaskRepository distributionTaskRepository,
            TaskExecutor taskExecutor,
            @Value("${aidrama.storage.download-dir:downloads/dramas}") Path downloadDir
    ) {
        this.repository = repository;
        this.baiduPanClient = baiduPanClient;
        this.mongoTemplate = mongoTemplate;
        this.dramaAiService = dramaAiService;
        this.categoryRepository = categoryRepository;
        this.mediaAccountRepository = mediaAccountRepository;
        this.distributionTaskRepository = distributionTaskRepository;
        this.taskExecutor = taskExecutor;
        this.downloadDir = downloadDir.toAbsolutePath().normalize();
    }

    public DramaController(
            DramaRepository repository,
            com.onehot.aidrama.baiduyun.BaiduPanClient baiduPanClient,
            MongoTemplate mongoTemplate,
            DramaAiService dramaAiService,
            DramaCategoryRepository categoryRepository,
            MediaAccountRepository mediaAccountRepository,
            DistributionTaskRepository distributionTaskRepository,
            TaskExecutor taskExecutor
    ) {
        this(
                repository,
                baiduPanClient,
                mongoTemplate,
                dramaAiService,
                categoryRepository,
                mediaAccountRepository,
                distributionTaskRepository,
                taskExecutor,
                Path.of("downloads/dramas")
        );
    }

    @GetMapping("/api/admin/dramas")
    ApiResponse<PageResult<Drama>> list(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) DramaStatus status,
            @RequestParam(required = false) List<String> categoryIds,
            @RequestParam(required = false) DramaAssetState assetState,
            @RequestParam(required = false) Integer episodeCount,
            @RequestParam(required = false) Instant createdFrom,
            @RequestParam(required = false) Instant createdTo,
        Pageable pageable
    ) {
        MongoPageQuery query = new MongoPageQuery()
                .containsAny(keyword, "title", "aiTitle", "summary", "sourcePath")
                .eq("status", status)
                .in("categoryIds", categoryIds)
                .arraySize("episodes", episodeCount)
                .range("createdAt", createdFrom, createdTo);
        if (assetState == DramaAssetState.MISSING_COVER) {
            query.missingText("coverUrl");
        } else if (assetState == DramaAssetState.MISSING_SUMMARY) {
            query.missingText("summary");
        }
        return ApiResponse.ok(PageResult.from(query.page(mongoTemplate, Drama.class, pageable)), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @GetMapping("/api/desktop/dramas")
    ApiResponse<PageResult<DramaDtos.DesktopDramaResponse>> desktopList(
            @AuthenticationPrincipal JwtPrincipal principal,
            @RequestParam(required = false) String keyword,
            Pageable pageable
    ) {
        Instant listedFrom = Instant.now().minus(7, ChronoUnit.DAYS);
        MongoPageQuery query = new MongoPageQuery()
                .containsAny(keyword, "title", "aiTitle")
                .eq("status", DramaStatus.READY)
                .range("createdAt", listedFrom, null);
        long total = mongoTemplate.count(query.toQuery(), Drama.class);
        Query pageQuery = query.toQuery().with(pageable);
        pageQuery.fields()
                .include("title", "aiTitle", "summary", "coverUrl", "aiCoverUrl", "rating", "categoryIds", "createdAt")
                .projectAs(MongoExpression.create("{ $size: { $ifNull: [ \"$episodes\", [] ] } }"), "episodeCount")
                .exclude("episodes");
        List<String> prioritizedDramaIds = prioritizedDramaIds(principal);
        Map<String, String> categoryNames = categoryRepository.findByEnabledTrueOrderBySortOrderAsc().stream()
                .collect(Collectors.toMap(
                        category -> category.getCode(),
                        category -> category.getName(),
                        (first, second) -> first
                ));
        List<DramaDtos.DesktopDramaResponse> content = mongoTemplate.find(pageQuery, Document.class, "dramas").stream()
                .map(document -> {
                    String id = documentId(document);
                    List<String> categoryIds = stringList(document, "categoryIds");
                    return DramaDtos.DesktopDramaResponse.from(
                            id,
                            document.getString("title"),
                            document.getString("aiTitle"),
                            document.getString("summary"),
                            document.getString("coverUrl"),
                            document.getString("aiCoverUrl"),
                            document.getInteger("rating"),
                            categoryIds,
                            categoryIds.stream()
                                .map(code -> categoryNames.getOrDefault(code, code))
                                .toList(),
                            intValue(document, "episodeCount"),
                            instantValue(document, "createdAt"),
                            prioritizedDramaIds.contains(id)
                    );
                })
                .toList();
        int pageSize = pageable.isPaged() ? pageable.getPageSize() : content.size();
        int pageNumber = pageable.isPaged() ? pageable.getPageNumber() : 0;
        int totalPages = pageSize == 0 ? 1 : (int) Math.ceil((double) total / pageSize);
        return ApiResponse.ok(
                new PageResult<>(content, total, totalPages, pageNumber, pageSize),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @GetMapping("/api/admin/dramas/{id}")
    ApiResponse<Drama> detail(@PathVariable String id) {
        return ApiResponse.ok(get(id), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @GetMapping("/api/admin/dramas/{id}/episodes")
    ApiResponse<List<DramaDtos.AdminEpisodeResponse>> adminEpisodes(@PathVariable String id) {
        Drama drama = get(id);
        List<DramaDtos.AdminEpisodeResponse> episodes = drama.getEpisodes().stream()
                .map(episode -> {
                    boolean downloaded = isDownloaded(id, episode.getEpisodeNo());
                    return new DramaDtos.AdminEpisodeResponse(
                            episode.getEpisodeNo(),
                            episode.getTitle(),
                            episode.getSourcePath(),
                            episode.getSize(),
                            downloaded,
                            downloaded ? "LOCAL" : "BAIDU",
                            downloaded ? adminEpisodeStreamUrl(id, episode.getEpisodeNo()) : null
                    );
                })
                .toList();
        return ApiResponse.ok(episodes, MDC.get(TraceIdFilter.TRACE_ID));
    }

    @GetMapping("/api/admin/dramas/{id}/episodes/{episodeNo}/play-url")
    ApiResponse<DramaDtos.EpisodePlaySource> adminEpisodePlaySource(
            @PathVariable String id,
            @PathVariable int episodeNo
    ) {
        DramaEpisode episode = getEpisode(id, episodeNo);
        if (isDownloaded(id, episodeNo)) {
            return ApiResponse.ok(
                    new DramaDtos.EpisodePlaySource(episodeNo, "LOCAL", true, adminEpisodeStreamUrl(id, episodeNo)),
                    MDC.get(TraceIdFilter.TRACE_ID)
            );
        }
        String playUrl = baiduPanClient.createDownloadUrls(List.of(episode.getSourcePath())).getFirst();
        return ApiResponse.ok(
                new DramaDtos.EpisodePlaySource(episodeNo, "BAIDU", false, playUrl),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @GetMapping("/api/admin/dramas/{id}/episodes/{episodeNo}/stream")
    ResponseEntity<?> streamAdminEpisode(
            @PathVariable String id,
            @PathVariable int episodeNo,
            @RequestHeader(value = HttpHeaders.RANGE, required = false) String range
    ) throws IOException {
        DramaEpisode episode = getEpisode(id, episodeNo);
        Path file = episodeFile(id, episodeNo);
        if (file.startsWith(downloadDir) && Files.isRegularFile(file)) {
            FileSystemResource resource = new FileSystemResource(file);
            MediaType mediaType = MediaTypeFactory.getMediaType(resource)
                    .orElse(MediaType.APPLICATION_OCTET_STREAM);
            return ResponseEntity.ok()
                    .contentType(mediaType)
                    .contentLength(resource.contentLength())
                    .header(HttpHeaders.ACCEPT_RANGES, "bytes")
                    .body(resource);
        }
        String playUrl = baiduPanClient.createDownloadUrls(List.of(episode.getSourcePath())).getFirst();
        return ResponseEntity.status(HttpStatus.FOUND)
                .location(URI.create(playUrl))
                .build();
    }

    @PostMapping("/api/admin/dramas")
    ApiResponse<Drama> create(@RequestBody DramaDtos.DramaRequest request) {
        return ApiResponse.ok(repository.save(apply(new Drama(), request)), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PutMapping("/api/admin/dramas/{id}")
    ApiResponse<Drama> update(@PathVariable String id, @RequestBody DramaDtos.DramaRequest request) {
        Drama drama = get(id);
        return ApiResponse.ok(repository.save(apply(drama, request)), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @DeleteMapping("/api/admin/dramas/{id}")
    ApiResponse<Void> delete(@PathVariable String id) {
        Drama drama = get(id);
        repository.delete(drama);
        return ApiResponse.ok(null, MDC.get(TraceIdFilter.TRACE_ID));
    }

    private Drama apply(Drama drama, DramaDtos.DramaRequest request) {
        drama.setTitle(request.title());
        drama.setAiTitle(request.aiTitle());
        drama.setSummary(request.summary());
        drama.setCoverUrl(request.coverUrl());
        drama.setAiCoverUrl(request.aiCoverUrl());
        drama.setRating(request.rating());
        drama.setCategoryIds(request.categoryIds());
        drama.setStatus(request.status());
        ensureReadyAllowed(drama);
        return drama;
    }

    @PostMapping("/api/admin/dramas/{id}/generate-title")
    ApiResponse<Drama> generateTitle(@PathVariable String id) {
        return ApiResponse.ok(dramaAiService.generateTitle(id), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PostMapping("/api/admin/dramas/{id}/generate-cover")
    ApiResponse<AiCoverGenerationAccepted> generateCover(@PathVariable String id) {
        Instant acceptedAt = Instant.now();
        Drama pending = get(id);
        pending.setAiCoverGenerating(true);
        repository.save(pending);
        taskExecutor.execute(() -> {
            try {
                Drama drama = dramaAiService.generateCover(id);
                LOGGER.info("AI cover generation finished: dramaId={}, aiCoverUrl={}", id, drama.getAiCoverUrl());
            } catch (RuntimeException exception) {
                LOGGER.error("AI cover generation failed: dramaId={}", id, exception);
                repository.findById(id).ifPresent(drama -> {
                    drama.setAiCoverGenerating(false);
                    repository.save(drama);
                });
            }
        });
        return ApiResponse.ok(
                new AiCoverGenerationAccepted(id, acceptedAt, acceptedAt.plus(1, ChronoUnit.MINUTES)),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @GetMapping("/api/desktop/dramas/{id}/download-plan")
    ApiResponse<DramaDtos.DownloadPlan> downloadPlan(@PathVariable String id) {
        Drama drama = get(id);
        List<DramaDtos.EpisodeDownload> episodes = drama.getEpisodes().stream()
                .map(episode -> new DramaDtos.EpisodeDownload(
                        episode.getEpisodeNo(),
                        episode.getSourcePath(),
                        "/api/desktop/dramas/" + id + "/episodes/" + episode.getEpisodeNo() + "/download"
                ))
                .toList();
        return ApiResponse.ok(
                new DramaDtos.DownloadPlan(
                        id,
                        effectiveTitle(drama),
                        drama.getAiTitle(),
                        drama.getSummary(),
                        drama.getCoverUrl(),
                        drama.getAiCoverUrl(),
                        effectiveCoverUrl(drama),
                        drama.getRating(),
                        drama.getCategoryIds(),
                        episodes
                ),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @GetMapping("/api/desktop/dramas/{id}/episodes/{episodeNo}/download")
    ResponseEntity<Void> downloadEpisode(@PathVariable String id, @PathVariable int episodeNo) {
        DramaEpisode episode = getEpisode(id, episodeNo);
        String downloadUrl = baiduPanClient.createDownloadUrls(List.of(episode.getSourcePath())).getFirst();
        return ResponseEntity.status(HttpStatus.FOUND)
                .location(URI.create(downloadUrl))
                .build();
    }

    private Drama get(String id) {
        return repository.findById(id)
                .orElseThrow(() -> new BusinessException("DRAMA_NOT_FOUND", "短剧不存在", HttpStatus.NOT_FOUND));
    }

    private DramaEpisode getEpisode(String id, int episodeNo) {
        return get(id).getEpisodes().stream()
                .filter(item -> item.getEpisodeNo() == episodeNo)
                .findFirst()
                .orElseThrow(() -> new BusinessException("EPISODE_NOT_FOUND", "剧集不存在", HttpStatus.NOT_FOUND));
    }

    private boolean isDownloaded(String dramaId, int episodeNo) {
        return Files.isRegularFile(episodeFile(dramaId, episodeNo));
    }

    private Path episodeFile(String dramaId, int episodeNo) {
        return downloadDir.resolve(dramaId).resolve("%03d.mp4".formatted(episodeNo)).normalize();
    }

    private String adminEpisodeStreamUrl(String dramaId, int episodeNo) {
        return "/api/admin/dramas/" + dramaId + "/episodes/" + episodeNo + "/stream";
    }

    private String effectiveCoverUrl(Drama drama) {
        if (drama.getAiCoverUrl() != null && !drama.getAiCoverUrl().isBlank()) {
            return drama.getAiCoverUrl();
        }
        return drama.getCoverUrl();
    }

    private String effectiveTitle(Drama drama) {
        if (hasText(drama.getAiTitle())) {
            return drama.getAiTitle();
        }
        return drama.getTitle();
    }

    private void ensureReadyAllowed(Drama drama) {
        if (drama.getStatus() != DramaStatus.READY) {
            return;
        }
        if (!hasText(drama.getAiTitle()) || !hasText(drama.getAiCoverUrl()) || drama.isAiCoverGenerating()
                || drama.getEpisodes() == null || drama.getEpisodes().isEmpty()) {
            throw new BusinessException(
                    "DRAMA_NOT_PREPARED",
                    "AI 剧名和 AI 封面生成完成后才能设为待分发",
                    HttpStatus.BAD_REQUEST
            );
        }
    }

    private boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    private List<String> prioritizedDramaIds(JwtPrincipal principal) {
        if (principal == null) {
            return List.of();
        }
        List<MediaAccount> mediaAccounts = Optional.ofNullable(mediaAccountRepository.findByOwnerAccountId(principal.accountId()))
                .orElse(List.of());
        List<String> mediaAccountIds = mediaAccounts.stream()
                .map(MediaAccount::getId)
                .toList();
        if (mediaAccountIds.isEmpty()) {
            return List.of();
        }
        return distributionTaskRepository.findByStatusAndPriorityGreaterThanAndMediaAccountIdIn(
                        DistributionTaskStatus.PENDING,
                        0,
                        mediaAccountIds
                ).stream()
                .map(DistributionTask::getDramaId)
                .toList();
    }

    private String documentId(Document document) {
        Object id = document.get("_id");
        if (id == null) {
            return document.getString("id");
        }
        return id.toString();
    }

    private List<String> stringList(Document document, String field) {
        List<?> values = document.getList(field, Object.class);
        if (values == null) {
            return List.of();
        }
        return values.stream()
                .map(String::valueOf)
                .toList();
    }

    private int intValue(Document document, String field) {
        Object value = document.get(field);
        if (value instanceof Number number) {
            return Math.max(number.intValue(), 0);
        }
        if (value instanceof String text && !text.isBlank()) {
            try {
                return Math.max(Integer.parseInt(text), 0);
            } catch (NumberFormatException ignored) {
                return 0;
            }
        }
        return 0;
    }

    private Instant instantValue(Document document, String field) {
        Object value = document.get(field);
        if (value instanceof Instant instant) {
            return instant;
        }
        if (value instanceof Date date) {
            return date.toInstant();
        }
        if (value instanceof String text && !text.isBlank()) {
            return Instant.parse(text);
        }
        return null;
    }

    public record AiCoverGenerationAccepted(String dramaId, Instant acceptedAt, Instant recommendedCheckAt) {
    }
}
