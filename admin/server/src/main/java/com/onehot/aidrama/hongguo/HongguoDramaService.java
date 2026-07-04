package com.onehot.aidrama.hongguo;

import com.onehot.aidrama.categories.DramaCategoryClassifier;
import com.onehot.aidrama.common.error.BusinessException;
import com.onehot.aidrama.dramas.Drama;
import com.onehot.aidrama.dramas.DramaDurationEstimator;
import com.onehot.aidrama.dramas.DramaEpisode;
import com.onehot.aidrama.dramas.DramaRepository;
import com.onehot.aidrama.dramas.DramaSources;
import com.onehot.aidrama.dramas.DramaStatus;
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
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;
import java.util.function.Supplier;

@Service
public class HongguoDramaService {
    public static final String PROVIDER = "52API_HONGGUO";
    private static final ZoneId CHINA_ZONE = ZoneId.of("Asia/Shanghai");
    private static final DateTimeFormatter CALENDAR_DATE_FORMATTER = DateTimeFormatter.BASIC_ISO_DATE;
    private static final Duration DOWNLOAD_URL_CACHE_SKEW = Duration.ofMinutes(2);
    private static final List<String> NON_LIVE_ACTION_KEYWORDS = List.of(
            "动漫",
            "动画",
            "漫画",
            "漫剧",
            "动态漫",
            "有声漫",
            "二次元",
            "国漫",
            "番剧",
            "卡通",
            "短漫",
            "沙雕动画",
            "ai动画",
            "ai漫"
    );

    private final HongguoApiClient apiClient;
    private final HongguoDramaCandidateRepository candidateRepository;
    private final DramaRepository dramaRepository;
    private final DramaCategoryClassifier classifier = new DramaCategoryClassifier();

    public HongguoDramaService(
            HongguoApiClient apiClient,
            HongguoDramaCandidateRepository candidateRepository,
            DramaRepository dramaRepository
    ) {
        this.apiClient = apiClient;
        this.candidateRepository = candidateRepository;
        this.dramaRepository = dramaRepository;
    }

    public CalendarSyncResult syncCalendar(LocalDate date, int page) {
        LocalDate effectiveDate = date == null ? LocalDate.now(CHINA_ZONE) : date;
        HongguoApiModels.CalendarPage calendarPage = callApi(() -> apiClient.fetchCalendar(effectiveDate, page));
        int created = 0;
        int updated = 0;
        int filtered = 0;
        String calendarDate = calendarDate(effectiveDate);
        for (HongguoApiModels.CalendarItem item : calendarPage.items()) {
            if (!hasText(item.providerDramaId())) {
                continue;
            }
            if (!isNonLiveActionCalendarItem(item)) {
                filtered++;
                continue;
            }
            HongguoDramaCandidate candidate = candidateRepository
                    .findByProviderAndProviderDramaId(PROVIDER, item.providerDramaId())
                    .orElseGet(HongguoDramaCandidate::new);
            boolean isNew = candidate.getId() == null;
            applyCandidate(candidate, item, calendarDate, calendarPage.page());
            candidateRepository.save(candidate);
            if (isNew) {
                created++;
            } else {
                updated++;
            }
        }
        return new CalendarSyncResult(
                effectiveDate,
                calendarPage.page(),
                calendarPage.items().size(),
                filtered,
                created,
                updated
        );
    }

    public List<HongguoDramaCandidate> listCandidates(LocalDate date) {
        if (date == null) {
            return candidateRepository.findTop50ByProviderOrderByCreatedAtDesc(PROVIDER);
        }
        return candidateRepository.findByProviderAndCalendarDateOrderByPublishedAtDesc(PROVIDER, calendarDate(date));
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
        String coverUrl = firstText(detail.coverUrl(), candidate.getCoverUrl());
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
            throw new BusinessException("HONGGUO_VIDEO_EMPTY", "红果播放接口没有返回可下载视频", HttpStatus.BAD_GATEWAY);
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

    private void applyCandidate(
            HongguoDramaCandidate candidate,
            HongguoApiModels.CalendarItem item,
            String calendarDate,
            int calendarPage
    ) {
        candidate.setProvider(PROVIDER);
        candidate.setProviderDramaId(item.providerDramaId());
        candidate.setTitle(item.title());
        candidate.setSummary(item.summary());
        candidate.setCoverUrl(item.coverUrl());
        candidate.setDuration(item.duration());
        candidate.setScore(item.score());
        candidate.setCategory(item.category());
        candidate.setCopyright(item.copyright());
        candidate.setEpisodeCount(item.episodeCount());
        candidate.setPlayCount(item.playCount());
        candidate.setPublishedAt(item.publishedAt());
        candidate.setCategories(item.categories());
        candidate.setCalendarDate(calendarDate);
        candidate.setCalendarPage(calendarPage);
    }

    private <T> T callApi(Supplier<T> supplier) {
        try {
            return supplier.get();
        } catch (HongguoApiException exception) {
            throw new BusinessException("HONGGUO_API_FAILED", exception.getMessage(), HttpStatus.BAD_GATEWAY);
        }
    }

    private boolean isNonLiveActionCalendarItem(HongguoApiModels.CalendarItem item) {
        return containsNonLiveActionKeyword(item.title())
                || containsNonLiveActionKeyword(item.summary())
                || containsNonLiveActionKeyword(item.category())
                || containsNonLiveActionKeyword(item.copyright())
                || containsNonLiveActionKeyword(item.categories())
                || containsNonLiveActionKeyword(item.recTags());
    }

    private boolean containsNonLiveActionKeyword(List<String> values) {
        if (values == null || values.isEmpty()) {
            return false;
        }
        return values.stream().anyMatch(this::containsNonLiveActionKeyword);
    }

    private boolean containsNonLiveActionKeyword(String value) {
        if (!hasText(value)) {
            return false;
        }
        String normalized = value.toLowerCase(Locale.ROOT);
        return NON_LIVE_ACTION_KEYWORDS.stream().anyMatch(normalized::contains);
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

    private static String sourcePath(String providerDramaId) {
        return "52api://hongguo/" + providerDramaId;
    }

    private static String videoSourcePath(String providerDramaId, String providerVideoId) {
        return sourcePath(providerDramaId) + "/video/" + providerVideoId;
    }

    private String calendarDate(LocalDate date) {
        return date.format(CALENDAR_DATE_FORMATTER);
    }

    private boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    public record CalendarSyncResult(LocalDate date, int page, int fetched, int filtered, int created, int updated) {
    }
}
