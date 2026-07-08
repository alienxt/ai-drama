package com.onehot.aidrama.hongguo;

import com.onehot.aidrama.categories.DramaCategoryClassifier;
import com.onehot.aidrama.common.error.BusinessException;
import com.onehot.aidrama.dramas.Drama;
import com.onehot.aidrama.dramas.DramaDurationEstimator;
import com.onehot.aidrama.dramas.DramaEpisode;
import com.onehot.aidrama.dramas.DramaRepository;
import com.onehot.aidrama.dramas.DramaSources;
import com.onehot.aidrama.dramas.DramaStatus;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.function.Supplier;

@Service
public class HongguoDramaService {
    public static final String PROVIDER = "52API_HONGGUO";
    private static final Duration DOWNLOAD_URL_CACHE_SKEW = Duration.ofMinutes(2);
    public static final Duration NEW_DRAMA_LOOKBACK = Duration.ofHours(3);
    public static final String DEFAULT_MANGA_KEYWORD = "漫剧";
    public static final String NEW_DRAMA_SCOPE = "HONGGUO_NEW_DRAMA";

    private final HongguoApiClient apiClient;
    private final HongguoDramaCandidateRepository candidateRepository;
    private final DramaRepository dramaRepository;
    private final HongguoCoverStorage coverStorage;
    private final DramaCategoryClassifier classifier = new DramaCategoryClassifier();
    private final Clock clock;

    @Autowired
    public HongguoDramaService(
            HongguoApiClient apiClient,
            HongguoDramaCandidateRepository candidateRepository,
            DramaRepository dramaRepository,
            HongguoCoverStorage coverStorage
    ) {
        this(apiClient, candidateRepository, dramaRepository, coverStorage, Clock.systemUTC());
    }

    HongguoDramaService(
            HongguoApiClient apiClient,
            HongguoDramaCandidateRepository candidateRepository,
            DramaRepository dramaRepository
    ) {
        this(apiClient, candidateRepository, dramaRepository, coverUrl -> coverUrl, Clock.systemUTC());
    }

    HongguoDramaService(
            HongguoApiClient apiClient,
            HongguoDramaCandidateRepository candidateRepository,
            DramaRepository dramaRepository,
            Clock clock
    ) {
        this(apiClient, candidateRepository, dramaRepository, coverUrl -> coverUrl, clock);
    }

    HongguoDramaService(
            HongguoApiClient apiClient,
            HongguoDramaCandidateRepository candidateRepository,
            DramaRepository dramaRepository,
            HongguoCoverStorage coverStorage,
            Clock clock
    ) {
        this.apiClient = apiClient;
        this.candidateRepository = candidateRepository;
        this.dramaRepository = dramaRepository;
        this.coverStorage = coverStorage;
        this.clock = clock;
    }

    public MangaSearchResult syncMangaSearch(String keyword, int page) {
        String effectiveKeyword = normalizeKeyword(keyword);
        int effectivePage = Math.max(page, 1);
        HongguoApiModels.MangaSearchPage searchPage = callApi(() -> apiClient.searchMangaDramas(effectiveKeyword, effectivePage));
        int created = 0;
        int updated = 0;
        int detailed = 0;
        int skipped = 0;
        for (HongguoApiModels.MangaSearchItem item : searchPage.items()) {
            if (!hasText(item.providerDramaId())) {
                skipped++;
                continue;
            }
            HongguoDramaCandidate candidate = candidateRepository
                    .findByProviderAndProviderDramaId(PROVIDER, item.providerDramaId())
                    .orElseGet(HongguoDramaCandidate::new);
            boolean isNew = candidate.getId() == null;
            HongguoApiModels.DramaDetail detail = callApi(() -> apiClient.fetchDetail(item.providerDramaId(), firstText(item.title(), effectiveKeyword)));
            detailed++;
            applyMangaCandidate(candidate, item, detail, effectiveKeyword, searchPage.page());
            candidateRepository.save(candidate);
            if (isNew) {
                created++;
            } else {
                updated++;
            }
        }
        return new MangaSearchResult(
                effectiveKeyword,
                searchPage.page(),
                searchPage.items().size(),
                detailed,
                skipped,
                created,
                updated
        );
    }

    public MangaSearchResult syncNewDramas(int page) {
        int effectivePage = Math.max(page, 1);
        Instant since = Instant.now(clock).minus(NEW_DRAMA_LOOKBACK);
        HongguoApiModels.MangaSearchPage searchPage = callApi(() -> apiClient.fetchNewDramas(effectivePage, since));
        int created = 0;
        int updated = 0;
        int detailed = 0;
        int skipped = 0;
        for (HongguoApiModels.MangaSearchItem item : searchPage.items()) {
            if (!hasText(item.providerDramaId())) {
                skipped++;
                continue;
            }
            HongguoDramaCandidate candidate = candidateRepository
                    .findByProviderAndProviderDramaId(PROVIDER, item.providerDramaId())
                    .orElseGet(HongguoDramaCandidate::new);
            boolean isNew = candidate.getId() == null;
            HongguoApiModels.DramaDetail detail = callApi(() -> apiClient.fetchDetail(item.providerDramaId(), firstText(item.title(), searchPage.keyword())));
            detailed++;
            applyNewDramaCandidate(candidate, item, detail, searchPage.page());
            candidateRepository.save(candidate);
            if (isNew) {
                created++;
            } else {
                updated++;
            }
        }
        return new MangaSearchResult(
                searchPage.keyword(),
                searchPage.page(),
                searchPage.items().size(),
                detailed,
                skipped,
                created,
                updated
        );
    }

    public List<HongguoDramaCandidate> listMangaCandidates(String keyword, Integer page) {
        int effectivePage = page == null ? 1 : Math.max(page, 1);
        if (hasText(keyword)) {
            return candidateRepository.findByProviderAndSearchKeywordAndSearchPageOrderByPublishedAtDescCreatedAtDesc(
                    PROVIDER,
                    keyword.trim(),
                    effectivePage
            );
        }
        return candidateRepository.findTop50ByProviderOrderByPublishedAtDescCreatedAtDesc(PROVIDER);
    }

    public List<HongguoDramaCandidate> listNewDramas(Integer page) {
        int effectivePage = page == null ? 1 : Math.max(page, 1);
        return candidateRepository.findByProviderAndCalendarDateAndCalendarPageOrderByPublishedAtDescCreatedAtDesc(
                PROVIDER,
                NEW_DRAMA_SCOPE,
                effectivePage
        );
    }

    public Drama importCandidate(String candidateId) {
        HongguoDramaCandidate candidate = candidateRepository.findById(candidateId)
                .orElseThrow(() -> new BusinessException("HONGGUO_CANDIDATE_NOT_FOUND", "红果候选短剧不存在", HttpStatus.NOT_FOUND));
        HongguoApiModels.DramaDetail detail = callApi(() -> apiClient.fetchDetail(candidate.getProviderDramaId(), candidate.getTitle()));
        if (detail.episodes().isEmpty()) {
            throw new BusinessException("HONGGUO_DETAIL_EMPTY", "红果详情没有返回剧集目录", HttpStatus.BAD_REQUEST);
        }

        String sourcePath = sourcePath(candidate.getProviderDramaId());
        Drama drama = dramaRepository.findAllBySourcePath(sourcePath).stream()
                .findFirst()
                .orElseGet(Drama::new);

        String title = firstText(detail.title(), candidate.getTitle());
        String summary = firstText(detail.summary(), candidate.getSummary());
        String coverUrl = coverStorage.store(firstText(detail.coverUrl(), candidate.getCoverUrl()));
        String previousSummary = drama.getSummary();

        drama.setTitle(title);
        drama.setSummary(summary);
        if (!Objects.equals(previousSummary, summary)) {
            drama.setAiSummary(null);
        }
        drama.setCoverUrl(coverUrl);
        drama.setSource(DramaSources.HONGGUO_52API);
        drama.setSourcePath(sourcePath);
        drama.setProviderName(PROVIDER);
        drama.setProviderDramaId(candidate.getProviderDramaId());
        drama.setPublishedAt(firstInstant(detail.publishedAt(), candidate.getPublishedAt()));
        drama.setSourceSyncedAt(Instant.now());
        if (drama.getStatus() != DramaStatus.DISABLED) {
            drama.setStatus(DramaStatus.READY);
        }
        drama.setCategoryIds(List.copyOf(categoryCodes(title, summary, candidate)));
        drama.setEpisodes(detail.episodes().stream()
                .map(episode -> episodeFrom(candidate.getProviderDramaId(), episode))
                .toList());
        setTotalMinutes(drama, detail);
        if (DramaDurationEstimator.needsCostAmountWan(drama)) {
            drama.setCostAmountWan(DramaDurationEstimator.estimateCostAmountWan(drama));
        }

        Drama saved = dramaRepository.save(drama);
        candidate.setStatus(HongguoCandidateStatus.IMPORTED);
        candidate.setImportedDramaId(saved.getId());
        candidateRepository.save(candidate);
        return saved;
    }

    public CoverBackfillResult backfillCovers() {
        List<Drama> dramas = dramaRepository.findAll().stream()
                .filter(this::isHongguoRecord)
                .toList();
        int updated = 0;
        int skipped = 0;
        int failed = 0;

        for (Drama drama : dramas) {
            String coverUrl = drama.getCoverUrl();
            if (!hasText(coverUrl) || coverUrl.startsWith("/uploads/")) {
                skipped++;
                continue;
            }

            String storedCoverUrl;
            try {
                storedCoverUrl = coverStorage.store(coverUrl);
            } catch (RuntimeException exception) {
                failed++;
                continue;
            }

            if (!hasText(storedCoverUrl) || Objects.equals(storedCoverUrl, coverUrl)) {
                failed++;
                continue;
            }

            drama.setCoverUrl(storedCoverUrl);
            dramaRepository.save(drama);
            updated++;
        }

        return new CoverBackfillResult(dramas.size(), updated, skipped, failed);
    }

    private boolean isHongguoRecord(Drama drama) {
        if (drama == null) {
            return false;
        }
        return DramaSources.isHongguo(drama.getSource())
                || startsWith(drama.getSourcePath(), "52api://hongguo/")
                || Objects.equals(PROVIDER, drama.getProviderName());
    }

    public URI createDownloadUri(Drama drama, DramaEpisode episode) {
        ensureHongguoEpisode(drama, episode);
        if (cachedDownloadUrlStillFresh(episode)) {
            return URI.create(episode.getDownloadUrl());
        }
        List<HongguoApiModels.VideoVariant> variants = callApi(() -> apiClient.fetchVideoVariants(
                drama.getProviderDramaId(),
                drama.getTitle(),
                episode.getProviderVideoId()
        ));
        if (variants.isEmpty()) {
            throw new BusinessException("HONGGUO_VIDEO_EMPTY", "红果播放接口没有返回可下载视频", HttpStatus.FAILED_DEPENDENCY);
        }
        HongguoApiModels.VideoVariant variant = variants.getFirst();
        HongguoApiModels.DecryptedUrl decryptedUrl = callApi(() -> apiClient.decrypt(variant.url(), variant.decryptKey()));
        episode.setDownloadUrl(decryptedUrl.url());
        episode.setDownloadUrlExpiresAt(decryptedUrl.expiresAt());
        dramaRepository.save(drama);
        return URI.create(decryptedUrl.url());
    }

    public void downloadEpisodeToFile(Drama drama, DramaEpisode episode, Path file) throws IOException {
        URI uri = createDownloadUri(drama, episode);
        Files.createDirectories(file.getParent());
        Path tempFile = file.resolveSibling(file.getFileName() + ".download");
        HttpClient httpClient = HttpClient.newBuilder()
                .followRedirects(HttpClient.Redirect.NORMAL)
                .connectTimeout(Duration.ofSeconds(30))
                .build();
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofMinutes(20))
                .GET()
                .build();
        try {
            HttpResponse<Path> response = httpClient.send(request, HttpResponse.BodyHandlers.ofFile(tempFile));
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new IOException("红果视频下载失败：HTTP " + response.statusCode());
            }
            Files.move(tempFile, file, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IOException("红果视频下载被中断", exception);
        } catch (IOException exception) {
            Files.deleteIfExists(tempFile);
            throw exception;
        }
    }

    private void applyMangaCandidate(
            HongguoDramaCandidate candidate,
            HongguoApiModels.MangaSearchItem item,
            HongguoApiModels.DramaDetail detail,
            String searchKeyword,
            int searchPage
    ) {
        applyCandidateFields(candidate, item, detail);
        candidate.setSearchKeyword(searchKeyword);
        candidate.setSearchPage(searchPage);
    }

    private void applyNewDramaCandidate(
            HongguoDramaCandidate candidate,
            HongguoApiModels.MangaSearchItem item,
            HongguoApiModels.DramaDetail detail,
            int page
    ) {
        applyCandidateFields(candidate, item, detail);
        candidate.setCalendarDate(NEW_DRAMA_SCOPE);
        candidate.setCalendarPage(page);
    }

    private void applyCandidateFields(
            HongguoDramaCandidate candidate,
            HongguoApiModels.MangaSearchItem item,
            HongguoApiModels.DramaDetail detail
    ) {
        candidate.setProvider(PROVIDER);
        candidate.setProviderDramaId(item.providerDramaId());
        candidate.setTitle(firstText(detail == null ? null : detail.title(), item.title()));
        candidate.setSummary(firstText(detail == null ? null : detail.summary(), item.summary()));
        candidate.setCoverUrl(firstText(detail == null ? null : detail.coverUrl(), item.coverUrl()));
        candidate.setDuration(item.duration());
        candidate.setScore(item.score());
        candidate.setCategory(item.category());
        candidate.setCopyright(item.copyright());
        candidate.setEpisodeCount(firstInteger(detail == null ? null : detail.episodeCount(), item.episodeCount()));
        candidate.setPlayCount(firstLong(detail == null ? null : detail.playCount(), item.playCount()));
        candidate.setPublishedAt(firstInstant(detail == null ? null : detail.publishedAt(), item.publishedAt()));
        candidate.setCategories(item.categories());
    }

    private <T> T callApi(Supplier<T> supplier) {
        try {
            return supplier.get();
        } catch (HongguoApiException exception) {
            throw new BusinessException("HONGGUO_API_FAILED", exception.getMessage(), HttpStatus.BAD_GATEWAY);
        }
    }

    private String normalizeKeyword(String keyword) {
        return hasText(keyword) ? keyword.trim() : DEFAULT_MANGA_KEYWORD;
    }

    private DramaEpisode episodeFrom(String providerDramaId, HongguoApiModels.DetailEpisode detailEpisode) {
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(detailEpisode.episodeNo());
        episode.setTitle(firstText(detailEpisode.title(), "第 %d 集".formatted(detailEpisode.episodeNo())));
        episode.setProviderVideoId(detailEpisode.providerVideoId());
        episode.setSourcePath(videoSourcePath(providerDramaId, detailEpisode.providerVideoId()));
        episode.setSize(0);
        return episode;
    }

    private void setTotalMinutes(Drama drama, HongguoApiModels.DramaDetail detail) {
        if (detail.durationSeconds() != null && detail.durationSeconds() > 0) {
            drama.setTotalMinutes((int) Math.ceil(detail.durationSeconds() / 60.0));
            return;
        }
        if (DramaDurationEstimator.needsTotalMinutes(drama)) {
            drama.setTotalMinutes(DramaDurationEstimator.estimateTotalMinutes(drama));
        }
    }

    private Set<String> categoryCodes(String title, String summary, HongguoDramaCandidate candidate) {
        Set<String> codes = new LinkedHashSet<>(classifier.classifyCodes(title, summary));
        mapRawCategory(candidate.getCategory(), codes);
        if (candidate.getCategories() != null) {
            candidate.getCategories().forEach(category -> mapRawCategory(category, codes));
        }
        if (codes.isEmpty()) {
            codes.add("general");
        }
        return codes;
    }

    private void mapRawCategory(String category, Set<String> codes) {
        if (!hasText(category)) {
            return;
        }
        String text = category.trim();
        if (text.contains("都市")) {
            codes.add("urban");
        }
        if (text.contains("古") || text.contains("穿越") || text.contains("权谋") || text.contains("玄幻") || text.contains("仙侠")) {
            codes.add("costume");
        }
        if (text.contains("逆袭") || text.contains("脑洞")) {
            codes.add("counterattack");
        }
        if (text.contains("甜") || text.contains("情感") || text.contains("婚") || text.contains("恋")) {
            codes.add("romance");
        }
        if (text.contains("医")) {
            codes.add("miracle-doctor");
        }
        if (text.contains("悬疑") || text.contains("灵异")) {
            codes.add("suspense");
        }
        if (text.contains("系统") || text.contains("科技")) {
            codes.add("sci-fi");
        }
        if (text.contains("美食") || text.contains("厨")) {
            codes.add("food");
        }
    }

    private void ensureHongguoEpisode(Drama drama, DramaEpisode episode) {
        if (drama == null || !DramaSources.isHongguo(drama.getSource())) {
            throw new BusinessException("DRAMA_SOURCE_NOT_HONGGUO", "当前短剧不是红果来源", HttpStatus.BAD_REQUEST);
        }
        if (!hasText(drama.getProviderDramaId())) {
            throw new BusinessException("HONGGUO_DRAMA_ID_MISSING", "红果短剧 ID 缺失", HttpStatus.BAD_REQUEST);
        }
        if (episode == null || !hasText(episode.getProviderVideoId())) {
            throw new BusinessException("HONGGUO_VIDEO_ID_MISSING", "红果剧集 video_id 缺失", HttpStatus.BAD_REQUEST);
        }
    }

    private boolean cachedDownloadUrlStillFresh(DramaEpisode episode) {
        return hasText(episode.getDownloadUrl())
                && episode.getDownloadUrlExpiresAt() != null
                && episode.getDownloadUrlExpiresAt().minus(DOWNLOAD_URL_CACHE_SKEW).isAfter(Instant.now());
    }

    private String firstText(String... values) {
        for (String value : values) {
            if (hasText(value)) {
                return value.trim();
            }
        }
        return null;
    }

    private Instant firstInstant(Instant... values) {
        for (Instant value : values) {
            if (value != null) {
                return value;
            }
        }
        return null;
    }

    private Integer firstInteger(Integer... values) {
        for (Integer value : values) {
            if (value != null) {
                return value;
            }
        }
        return null;
    }

    private Long firstLong(Long... values) {
        for (Long value : values) {
            if (value != null) {
                return value;
            }
        }
        return null;
    }

    private static String sourcePath(String providerDramaId) {
        return "52api://hongguo/" + providerDramaId;
    }

    private static String videoSourcePath(String providerDramaId, String providerVideoId) {
        return sourcePath(providerDramaId) + "/video/" + providerVideoId;
    }

    private boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    private boolean startsWith(String value, String prefix) {
        return value != null && value.startsWith(prefix);
    }

    public record MangaSearchResult(String keyword, int page, int fetched, int detailed, int skipped, int created, int updated) {
    }

    public record CoverBackfillResult(int requested, int updated, int skipped, int failed) {
    }
}
