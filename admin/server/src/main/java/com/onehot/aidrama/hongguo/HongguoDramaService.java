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
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.function.Supplier;

@Service
public class HongguoDramaService {
    public static final String PROVIDER = "52API_HONGGUO";
    private static final Duration DOWNLOAD_URL_CACHE_SKEW = Duration.ofMinutes(2);
    private static final ZoneId CHINA_ZONE = ZoneId.of("Asia/Shanghai");
    public static final Duration NEW_DRAMA_LOOKBACK = Duration.ofHours(3);
    public static final Duration AI_MANGA_NEW_LOOKBACK = Duration.ofDays(3);
    public static final int DEFAULT_AI_MANGA_SYNC_MAX_PAGES = 8;
    public static final int DEFAULT_NEW_PLAY_AUTO_IMPORT_MAX_PAGES = 5;
    public static final String DEFAULT_MANGA_KEYWORD = "漫剧";
    public static final String NEW_DRAMA_SCOPE = "HONGGUO_NEW_DRAMA";
    public static final String AI_MANGA_RECENT_SCOPE = "HONGGUO_AI_MANGA_DAYS_3";
    public static final String AI_PLAYLET_NEW_TOP_SCOPE = "HONGGUO_AI_PLAYLET_NEW_TOP";
    private static final String AI_MANGA_RECENT_LABEL = "AI漫剧近3日上新60-120分钟";
    private static final String AI_MANGA_RECENT_SEARCH_KEYWORD = "AI漫剧近3日上新";
    private static final String AI_PLAYLET_NEW_TOP_LABEL = "AI剧新剧榜";

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

    public MangaSearchResult syncAiPlayletNewTopDramas(int page) {
        int effectivePage = Math.max(page, 1);
        HongguoApiModels.MangaSearchPage searchPage = callApi(() -> apiClient.fetchAiPlayletNewTopDramas(effectivePage));
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
            applyAiPlayletNewTopCandidate(candidate, item, detail, searchPage.page());
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

    public MangaSearchResult syncAiMangaNewDramas(int maxPages) {
        int effectiveMaxPages = Math.max(1, maxPages);
        Instant since = Instant.now(clock).minus(AI_MANGA_NEW_LOOKBACK);
        LinkedHashSet<String> filterIds = new LinkedHashSet<>();
        String sessionId = null;
        int pagesFetched = 0;
        int fetched = 0;
        int created = 0;
        int updated = 0;
        int skipped = 0;

        for (int pageNumber = 1; pageNumber <= effectiveMaxPages; pageNumber++) {
            int currentPage = pageNumber;
            String requestSessionId = sessionId;
            List<String> requestFilterIds = List.copyOf(filterIds);
            HongguoApiModels.MangaSearchPage searchPage = callApi(
                    () -> apiClient.fetchScreenedAiMangaNewDramas(currentPage, requestSessionId, requestFilterIds)
            );
            CandidateSyncResult syncResult = saveAiMangaSearchPage(searchPage, since);
            MangaSearchResult pageResult = syncResult.result();
            pagesFetched++;
            fetched += pageResult.fetched();
            created += pageResult.created();
            updated += pageResult.updated();
            skipped += pageResult.skipped();
            if (hasText(searchPage.sessionId())) {
                sessionId = searchPage.sessionId().trim();
            }
            filterIds.addAll(searchPage.filterIds());
            if (searchPage.items().isEmpty()) {
                break;
            }
        }

        return new MangaSearchResult(
                AI_MANGA_RECENT_LABEL,
                pagesFetched,
                fetched,
                0,
                skipped,
                created,
                updated
        );
    }

    public AutoImportResult autoImportAiMangaNewDramas(int limit, int maxPages) {
        int effectiveLimit = Math.max(1, limit);
        int effectiveMaxPages = Math.max(1, maxPages);
        LinkedHashMap<String, HongguoDramaCandidate> queuedCandidates = new LinkedHashMap<>();
        LinkedHashSet<String> filterIds = new LinkedHashSet<>();
        String sessionId = null;
        int pagesFetched = 0;
        int candidatesFetched = 0;
        int created = 0;
        int updated = 0;
        int skipped = 0;
        int skippedExisting = 0;
        Instant since = Instant.now(clock).minus(AI_MANGA_NEW_LOOKBACK);

        for (int pageNumber = 1; pageNumber <= effectiveMaxPages && queuedCandidates.size() < effectiveLimit; pageNumber++) {
            int currentPage = pageNumber;
            String requestSessionId = sessionId;
            List<String> requestFilterIds = List.copyOf(filterIds);
            HongguoApiModels.MangaSearchPage searchPage = callApi(
                    () -> apiClient.fetchScreenedAiMangaNewDramas(currentPage, requestSessionId, requestFilterIds)
            );
            CandidateSyncResult syncResult = saveAiMangaSearchPage(searchPage, since);
            MangaSearchResult pageResult = syncResult.result();
            pagesFetched++;
            candidatesFetched += pageResult.fetched();
            created += pageResult.created();
            updated += pageResult.updated();
            skipped += pageResult.skipped();
            if (hasText(searchPage.sessionId())) {
                sessionId = searchPage.sessionId().trim();
            }
            filterIds.addAll(searchPage.filterIds());

            for (HongguoDramaCandidate candidate : syncResult.candidates()) {
                if (!hasText(candidate.getProviderDramaId()) || queuedCandidates.containsKey(candidate.getProviderDramaId())) {
                    continue;
                }
                if (isAlreadyImportedOrExisting(candidate)) {
                    skippedExisting++;
                    continue;
                }
                queuedCandidates.put(candidate.getProviderDramaId(), candidate);
                if (queuedCandidates.size() >= effectiveLimit) {
                    break;
                }
            }
            if (searchPage.items().isEmpty()) {
                break;
            }
        }

        List<ImportedDramaSummary> importedDramas = new ArrayList<>();
        List<AutoImportFailure> failures = new ArrayList<>();
        for (HongguoDramaCandidate candidate : queuedCandidates.values()) {
            if (importedDramas.size() >= effectiveLimit) {
                break;
            }
            if (isAlreadyImportedOrExisting(candidate)) {
                skippedExisting++;
                continue;
            }
            if (!hasText(candidate.getId())) {
                failures.add(failure(candidate, "候选短剧 ID 缺失，无法导入"));
                continue;
            }
            try {
                Drama drama = importCandidate(candidate.getId());
                importedDramas.add(summary(drama));
            } catch (RuntimeException exception) {
                failures.add(failure(candidate, exception.getMessage()));
            }
        }

        return new AutoImportResult(
                effectiveLimit,
                effectiveMaxPages,
                pagesFetched,
                candidatesFetched,
                created,
                updated,
                skipped,
                queuedCandidates.size(),
                importedDramas.size(),
                skippedExisting,
                failures.size(),
                importedDramas,
                failures
        );
    }

    public NewPlayAutoImportResult autoImportTodayNewPlayDramas(int maxPages) {
        return autoImportNewPlayDramas(LocalDate.now(clock.withZone(CHINA_ZONE)), maxPages);
    }

    NewPlayAutoImportResult autoImportNewPlayDramas(LocalDate date, int maxPages) {
        LocalDate effectiveDate = date == null ? LocalDate.now(clock.withZone(CHINA_ZONE)) : date;
        int effectiveMaxPages = Math.min(Math.max(1, maxPages), DEFAULT_NEW_PLAY_AUTO_IMPORT_MAX_PAGES);
        LinkedHashSet<String> seenProviderDramaIds = new LinkedHashSet<>();
        List<ImportedDramaSummary> importedDramas = new ArrayList<>();
        List<AutoImportFailure> failures = new ArrayList<>();
        int pagesFetched = 0;
        int candidatesFetched = 0;
        int created = 0;
        int updated = 0;
        int skipped = 0;
        int skippedExisting = 0;

        for (int pageNumber = 1; pageNumber <= effectiveMaxPages; pageNumber++) {
            HongguoApiModels.MangaSearchPage searchPage;
            try {
                searchPage = apiClient.fetchNewDramas(pageNumber, effectiveDate);
            } catch (HongguoApiException exception) {
                if (pageNumber == 1) {
                    throw exception;
                }
                break;
            }
            pagesFetched++;
            if (searchPage.items().isEmpty()) {
                break;
            }
            candidatesFetched += searchPage.items().size();

            for (HongguoApiModels.MangaSearchItem item : searchPage.items()) {
                if (!hasText(item.providerDramaId())) {
                    skipped++;
                    continue;
                }
                if (!seenProviderDramaIds.add(item.providerDramaId().trim())) {
                    skipped++;
                    continue;
                }
                HongguoDramaCandidate candidate = candidateRepository
                        .findByProviderAndProviderDramaId(PROVIDER, item.providerDramaId())
                        .orElseGet(HongguoDramaCandidate::new);
                boolean isNew = candidate.getId() == null;
                applyNewDramaCandidate(candidate, item, null, searchPage.page());
                HongguoDramaCandidate saved = candidateRepository.save(candidate);
                if (isNew) {
                    created++;
                } else {
                    updated++;
                }
                if (isAlreadyImportedOrExisting(saved)) {
                    skippedExisting++;
                    continue;
                }
                if (!hasText(saved.getId())) {
                    failures.add(failure(saved, "候选短剧 ID 缺失，无法导入"));
                    continue;
                }
                try {
                    Drama drama = importCandidate(saved.getId());
                    importedDramas.add(summary(drama));
                } catch (RuntimeException exception) {
                    failures.add(failure(saved, exception.getMessage()));
                }
            }
        }

        return new NewPlayAutoImportResult(
                effectiveDate.toString(),
                effectiveMaxPages,
                pagesFetched,
                candidatesFetched,
                created,
                updated,
                skipped,
                importedDramas.size(),
                skippedExisting,
                failures.size(),
                importedDramas,
                failures
        );
    }

    private CandidateSyncResult saveAiMangaSearchPage(HongguoApiModels.MangaSearchPage searchPage, Instant publishedSince) {
        int created = 0;
        int updated = 0;
        int skipped = 0;
        List<HongguoDramaCandidate> candidates = new ArrayList<>();
        for (HongguoApiModels.MangaSearchItem item : searchPage.items()) {
            if (!hasText(item.providerDramaId())) {
                skipped++;
                continue;
            }
            if (!isRecentOrUnknown(item.publishedAt(), publishedSince)) {
                skipped++;
                continue;
            }
            HongguoDramaCandidate candidate = candidateRepository
                    .findByProviderAndProviderDramaId(PROVIDER, item.providerDramaId())
                    .orElseGet(HongguoDramaCandidate::new);
            boolean isNew = candidate.getId() == null;
            applyAiMangaCandidate(candidate, item, searchPage.page());
            HongguoDramaCandidate saved = candidateRepository.save(candidate);
            candidates.add(saved);
            if (isNew) {
                created++;
            } else {
                updated++;
            }
        }
        return new CandidateSyncResult(
                new MangaSearchResult(
                        searchPage.keyword(),
                        searchPage.page(),
                        searchPage.items().size(),
                        0,
                        skipped,
                        created,
                        updated
                ),
                candidates
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

    public List<HongguoDramaCandidate> listAiPlayletNewTopDramas(Integer page) {
        int effectivePage = page == null ? 1 : Math.max(page, 1);
        return candidateRepository.findByProviderAndCalendarDateAndCalendarPageOrderByPublishedAtDescCreatedAtDesc(
                PROVIDER,
                AI_PLAYLET_NEW_TOP_SCOPE,
                effectivePage
        );
    }

    public List<HongguoDramaCandidate> listAiMangaNewDramas(Integer page) {
        Instant since = Instant.now(clock).minus(AI_MANGA_NEW_LOOKBACK);
        return candidateRepository.findByProviderAndCalendarDateOrderByPublishedAtDesc(
                PROVIDER,
                AI_MANGA_RECENT_SCOPE
        ).stream()
                .filter(candidate -> candidate.getStatus() != HongguoCandidateStatus.IMPORTED)
                .filter(candidate -> isRecentOrUnknown(candidate.getPublishedAt(), since))
                .limit(50)
                .toList();
    }

    public List<HongguoApiModels.ChannelOption> listOtherChannelOptions(String channelCode) {
        OtherShortDramaChannel channel = OtherShortDramaChannel.fromCode(channelCode);
        if (!channel.needsOption()) {
            return List.of();
        }
        return callApi(() -> apiClient.fetchOtherChannelOptions(channel));
    }

    public List<HongguoDramaCandidate> listOtherChannelCandidates(
            String channelCode,
            String keyword,
            String optionId,
            Integer page
    ) {
        OtherShortDramaChannel channel = OtherShortDramaChannel.fromCode(channelCode);
        int effectivePage = page == null ? 1 : Math.max(page, 1);
        String scope = otherChannelScope(channel, keyword, optionId);
        if (!hasText(scope)) {
            return List.of();
        }
        return candidateRepository.findByProviderAndSearchKeywordAndSearchPageOrderByPublishedAtDescCreatedAtDesc(
                channel.providerCode(),
                scope,
                effectivePage
        );
    }

    public MangaSearchResult syncOtherChannel(String channelCode, String keyword, String optionId, int page) {
        OtherShortDramaChannel channel = OtherShortDramaChannel.fromCode(channelCode);
        int effectivePage = Math.max(page, 1);
        String effectiveOptionId = normalizeOtherOption(channel, optionId);
        String effectiveKeyword = channel.supportsKeyword() ? normalizeOtherKeyword(channel, keyword) : null;
        HongguoApiModels.MangaSearchPage searchPage = callApi(
                () -> apiClient.fetchOtherChannelDramas(channel, effectiveKeyword, effectiveOptionId, effectivePage)
        );

        int created = 0;
        int updated = 0;
        int detailed = 0;
        int skipped = 0;
        String scope = otherChannelScope(channel, effectiveKeyword, effectiveOptionId);
        for (HongguoApiModels.MangaSearchItem item : searchPage.items()) {
            if (!hasText(item.providerDramaId())) {
                skipped++;
                continue;
            }
            HongguoDramaCandidate candidate = candidateRepository
                    .findByProviderAndProviderDramaId(channel.providerCode(), item.providerDramaId())
                    .orElseGet(HongguoDramaCandidate::new);
            boolean isNew = candidate.getId() == null;
            HongguoApiModels.DramaDetail detail = callApi(
                    () -> apiClient.fetchOtherDetail(channel, item.providerDramaId(), firstText(item.title(), effectiveKeyword, channel.label()))
            );
            detailed++;
            applyOtherChannelCandidate(candidate, channel, item, detail, scope, effectivePage);
            candidateRepository.save(candidate);
            if (isNew) {
                created++;
            } else {
                updated++;
            }
        }
        return new MangaSearchResult(
                otherChannelResultLabel(channel, effectiveKeyword, effectiveOptionId),
                searchPage.page(),
                searchPage.items().size(),
                detailed,
                skipped,
                created,
                updated
        );
    }

    public Drama importCandidate(String candidateId) {
        HongguoDramaCandidate candidate = candidateRepository.findById(candidateId)
                .orElseThrow(() -> new BusinessException("HONGGUO_CANDIDATE_NOT_FOUND", "红果候选短剧不存在", HttpStatus.NOT_FOUND));
        HongguoApiModels.DramaDetail detail = fetchCandidateDetail(candidate);
        if (detail.episodes().isEmpty()) {
            throw new BusinessException("HONGGUO_DETAIL_EMPTY", "52API 详情没有返回剧集目录", HttpStatus.BAD_REQUEST);
        }

        String sourcePath = sourcePath(candidate);
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
        drama.setProviderName(normalizeProvider(candidate.getProvider()));
        drama.setProviderDramaId(candidate.getProviderDramaId());
        drama.setPublishedAt(firstInstant(detail.publishedAt(), candidate.getPublishedAt()));
        drama.setSourceSyncedAt(Instant.now());
        if (drama.getStatus() != DramaStatus.DISABLED) {
            drama.setStatus(DramaStatus.READY);
        }
        drama.setCategoryIds(List.copyOf(categoryCodes(title, summary, candidate)));
        drama.setEpisodes(detail.episodes().stream()
                .map(episode -> episodeFrom(candidate, episode))
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
        ensureFiftyTwoApiEpisode(drama, episode);
        if (cachedDownloadUrlStillFresh(episode)) {
            return URI.create(episode.getDownloadUrl());
        }
        List<HongguoApiModels.VideoVariant> variants = fetchCandidateVideoVariants(drama, episode);
        if (variants.isEmpty()) {
            throw new BusinessException("HONGGUO_VIDEO_EMPTY", "52API 播放接口没有返回可下载视频", HttpStatus.FAILED_DEPENDENCY);
        }
        HongguoApiModels.VideoVariant variant = variants.getFirst();
        if (hasText(variant.decryptKey())) {
            HongguoApiModels.DecryptedUrl decryptedUrl = callApi(() -> apiClient.decrypt(variant.url(), variant.decryptKey()));
            episode.setDownloadUrl(decryptedUrl.url());
            episode.setDownloadUrlExpiresAt(decryptedUrl.expiresAt());
        } else {
            episode.setDownloadUrl(variant.url());
            episode.setDownloadUrlExpiresAt(Instant.now(clock).plus(Duration.ofHours(6)));
        }
        dramaRepository.save(drama);
        return URI.create(episode.getDownloadUrl());
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

    private void applyAiMangaCandidate(
            HongguoDramaCandidate candidate,
            HongguoApiModels.MangaSearchItem item,
            int page
    ) {
        applyCandidateFields(candidate, item, null);
        candidate.setCalendarDate(AI_MANGA_RECENT_SCOPE);
        candidate.setCalendarPage(page);
        candidate.setSearchKeyword(AI_MANGA_RECENT_SEARCH_KEYWORD);
        candidate.setSearchPage(page);
        candidate.setCategories(mergedCategories(candidate.getCategories(), "AI漫剧", "近3日上新"));
    }

    private void applyAiPlayletNewTopCandidate(
            HongguoDramaCandidate candidate,
            HongguoApiModels.MangaSearchItem item,
            HongguoApiModels.DramaDetail detail,
            int page
    ) {
        applyCandidateFields(candidate, item, detail);
        candidate.setCalendarDate(AI_PLAYLET_NEW_TOP_SCOPE);
        candidate.setCalendarPage(page);
        candidate.setSearchKeyword(AI_PLAYLET_NEW_TOP_LABEL);
        candidate.setSearchPage(page);
        candidate.setCategories(mergedCategories(candidate.getCategories(), "AI剧", "新剧榜"));
    }

    private void applyOtherChannelCandidate(
            HongguoDramaCandidate candidate,
            OtherShortDramaChannel channel,
            HongguoApiModels.MangaSearchItem item,
            HongguoApiModels.DramaDetail detail,
            String scope,
            int page
    ) {
        applyCandidateFields(candidate, item, detail);
        candidate.setProvider(channel.providerCode());
        candidate.setSearchKeyword(scope);
        candidate.setSearchPage(page);
        candidate.setCategories(mergedCategories(candidate.getCategories(), channel.label()));
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

    private HongguoApiModels.DramaDetail fetchCandidateDetail(HongguoDramaCandidate candidate) {
        if (isHongguoProvider(candidate.getProvider())) {
            return callApi(() -> apiClient.fetchDetail(candidate.getProviderDramaId(), candidate.getTitle()));
        }
        OtherShortDramaChannel channel = OtherShortDramaChannel.fromProviderCode(normalizeProvider(candidate.getProvider()));
        return callApi(() -> apiClient.fetchOtherDetail(channel, candidate.getProviderDramaId(), candidate.getTitle()));
    }

    private List<HongguoApiModels.VideoVariant> fetchCandidateVideoVariants(Drama drama, DramaEpisode episode) {
        if (isHongguoProvider(drama.getProviderName())) {
            return callApi(() -> apiClient.fetchVideoVariants(
                    drama.getProviderDramaId(),
                    drama.getTitle(),
                    episode.getProviderVideoId()
            ));
        }
        OtherShortDramaChannel channel = OtherShortDramaChannel.fromProviderCode(normalizeProvider(drama.getProviderName()));
        if (!channel.detailChannel().supportsVideo()) {
            if (hasText(episode.getDownloadUrl())) {
                return List.of(new HongguoApiModels.VideoVariant(
                        episode.getDownloadUrl(),
                        null,
                        null,
                        null,
                        null,
                        null,
                        null
                ));
            }
            throw new BusinessException("HONGGUO_VIDEO_UNSUPPORTED", channel.label() + "暂未提供单集播放解析接口", HttpStatus.FAILED_DEPENDENCY);
        }
        return callApi(() -> apiClient.fetchOtherVideoVariants(
                channel,
                drama.getProviderDramaId(),
                drama.getTitle(),
                episode.getProviderVideoId()
        ));
    }

    private boolean isRecentOrUnknown(Instant publishedAt, Instant since) {
        return publishedAt == null || since == null || !publishedAt.isBefore(since);
    }

    private String normalizeKeyword(String keyword) {
        return hasText(keyword) ? keyword.trim() : DEFAULT_MANGA_KEYWORD;
    }

    private String normalizeOtherKeyword(OtherShortDramaChannel channel, String keyword) {
        return hasText(keyword) ? keyword.trim() : firstText(channel.defaultKeyword(), channel.label());
    }

    private String normalizeOtherOption(OtherShortDramaChannel channel, String optionId) {
        if (!channel.needsOption()) {
            return null;
        }
        if (hasText(optionId)) {
            return optionId.trim();
        }
        List<HongguoApiModels.ChannelOption> options = listOtherChannelOptions(channel.code());
        if (options.isEmpty()) {
            throw new BusinessException("OTHER_CHANNEL_OPTION_EMPTY", channel.label() + "没有返回可用榜单或分类", HttpStatus.BAD_GATEWAY);
        }
        return options.getFirst().id();
    }

    private String otherChannelScope(OtherShortDramaChannel channel, String keyword, String optionId) {
        if (channel.supportsKeyword()) {
            return "OTHER:%s:SEARCH:%s".formatted(channel.code(), normalizeOtherKeyword(channel, keyword));
        }
        if (!hasText(optionId)) {
            return null;
        }
        return "OTHER:%s:OPTION:%s".formatted(channel.code(), optionId.trim());
    }

    private String otherChannelResultLabel(OtherShortDramaChannel channel, String keyword, String optionId) {
        if (channel.supportsKeyword()) {
            return channel.label() + "：" + normalizeOtherKeyword(channel, keyword);
        }
        return channel.label() + "：" + optionId;
    }

    private DramaEpisode episodeFrom(HongguoDramaCandidate candidate, HongguoApiModels.DetailEpisode detailEpisode) {
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(detailEpisode.episodeNo());
        episode.setTitle(firstText(detailEpisode.title(), "第 %d 集".formatted(detailEpisode.episodeNo())));
        episode.setProviderVideoId(detailEpisode.providerVideoId());
        episode.setSourcePath(videoSourcePath(candidate, detailEpisode.providerVideoId()));
        if (hasText(detailEpisode.downloadUrl())) {
            episode.setDownloadUrl(detailEpisode.downloadUrl().trim());
            episode.setDownloadUrlExpiresAt(Instant.now(clock).plus(Duration.ofHours(6)));
        }
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

    private void ensureFiftyTwoApiEpisode(Drama drama, DramaEpisode episode) {
        if (drama == null || !DramaSources.isHongguo(drama.getSource())) {
            throw new BusinessException("DRAMA_SOURCE_NOT_HONGGUO", "当前短剧不是 52API 来源", HttpStatus.BAD_REQUEST);
        }
        if (!hasText(drama.getProviderDramaId())) {
            throw new BusinessException("HONGGUO_DRAMA_ID_MISSING", "52API 短剧 ID 缺失", HttpStatus.BAD_REQUEST);
        }
        if (episode == null || (!hasText(episode.getProviderVideoId()) && !hasText(episode.getDownloadUrl()))) {
            throw new BusinessException("HONGGUO_VIDEO_ID_MISSING", "52API 剧集 video_id 缺失", HttpStatus.BAD_REQUEST);
        }
    }

    private boolean cachedDownloadUrlStillFresh(DramaEpisode episode) {
        return hasText(episode.getDownloadUrl())
                && episode.getDownloadUrlExpiresAt() != null
                && episode.getDownloadUrlExpiresAt().minus(DOWNLOAD_URL_CACHE_SKEW).isAfter(Instant.now());
    }

    private boolean isAlreadyImportedOrExisting(HongguoDramaCandidate candidate) {
        if (candidate == null) {
            return true;
        }
        if (candidate.getStatus() == HongguoCandidateStatus.IMPORTED) {
            return true;
        }
        Optional<Drama> existingDrama = existingDrama(candidate);
        if (existingDrama.isEmpty()) {
            return false;
        }
        Drama drama = existingDrama.get();
        candidate.setStatus(HongguoCandidateStatus.IMPORTED);
        candidate.setImportedDramaId(drama.getId());
        candidateRepository.save(candidate);
        return true;
    }

    private Optional<Drama> existingDrama(HongguoDramaCandidate candidate) {
        if (candidate == null || !hasText(candidate.getProviderDramaId())) {
            return Optional.empty();
        }
        return dramaRepository.findAllBySourcePath(sourcePath(candidate)).stream().findFirst();
    }

    private ImportedDramaSummary summary(Drama drama) {
        return new ImportedDramaSummary(
                drama.getId(),
                drama.getTitle(),
                drama.getProviderDramaId(),
                drama.getSourcePath()
        );
    }

    private AutoImportFailure failure(HongguoDramaCandidate candidate, String errorMessage) {
        return new AutoImportFailure(
                candidate == null ? null : candidate.getId(),
                candidate == null ? null : candidate.getProviderDramaId(),
                candidate == null ? null : candidate.getTitle(),
                firstText(errorMessage, "导入失败")
        );
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

    private List<String> mergedCategories(List<String> categories, String... required) {
        LinkedHashSet<String> values = new LinkedHashSet<>();
        if (categories != null) {
            categories.stream()
                    .filter(this::hasText)
                    .map(String::trim)
                    .forEach(values::add);
        }
        if (required != null) {
            for (String value : required) {
                if (hasText(value)) {
                    values.add(value.trim());
                }
            }
        }
        return List.copyOf(values);
    }

    private String normalizeProvider(String provider) {
        return hasText(provider) ? provider.trim() : PROVIDER;
    }

    private boolean isHongguoProvider(String provider) {
        return PROVIDER.equals(normalizeProvider(provider));
    }

    private String sourcePath(HongguoDramaCandidate candidate) {
        return sourcePath(normalizeProvider(candidate.getProvider()), candidate.getProviderDramaId());
    }

    private String sourcePath(String provider, String providerDramaId) {
        if (PROVIDER.equals(normalizeProvider(provider))) {
            return "52api://hongguo/" + providerDramaId;
        }
        OtherShortDramaChannel channel = OtherShortDramaChannel.fromProviderCode(normalizeProvider(provider));
        return "52api://" + channel.code().toLowerCase() + "/" + providerDramaId;
    }

    private String videoSourcePath(HongguoDramaCandidate candidate, String providerVideoId) {
        return sourcePath(candidate) + "/video/" + providerVideoId;
    }

    private boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    private boolean startsWith(String value, String prefix) {
        return value != null && value.startsWith(prefix);
    }

    public record MangaSearchResult(String keyword, int page, int fetched, int detailed, int skipped, int created, int updated) {
    }

    public record AutoImportResult(
            int requested,
            int maxPages,
            int pagesFetched,
            int candidatesFetched,
            int created,
            int updated,
            int skipped,
            int queued,
            int imported,
            int skippedExisting,
            int failed,
            List<ImportedDramaSummary> importedDramas,
            List<AutoImportFailure> failures
    ) {
    }

    public record ImportedDramaSummary(String id, String title, String providerDramaId, String sourcePath) {
    }

    public record AutoImportFailure(String candidateId, String providerDramaId, String title, String errorMessage) {
    }

    public record NewPlayAutoImportResult(
            String date,
            int maxPages,
            int pagesFetched,
            int candidatesFetched,
            int created,
            int updated,
            int skipped,
            int imported,
            int skippedExisting,
            int failed,
            List<ImportedDramaSummary> importedDramas,
            List<AutoImportFailure> failures
    ) {
    }

    public record CoverBackfillResult(int requested, int updated, int skipped, int failed) {
    }

    private record CandidateSyncResult(MangaSearchResult result, List<HongguoDramaCandidate> candidates) {
    }
}
