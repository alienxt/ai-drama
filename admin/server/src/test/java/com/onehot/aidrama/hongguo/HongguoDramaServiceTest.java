package com.onehot.aidrama.hongguo;

import com.onehot.aidrama.common.error.BusinessException;
import com.onehot.aidrama.dramas.Drama;
import com.onehot.aidrama.dramas.DramaEpisode;
import com.onehot.aidrama.dramas.DramaRepository;
import com.onehot.aidrama.dramas.DramaSources;
import com.onehot.aidrama.dramas.DramaStatus;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.HttpStatus;

import java.net.URI;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class HongguoDramaServiceTest {
    @Test
    void syncMangaSearchFetchesDetailsForAllSearchPageCandidates() {
        HongguoApiClient apiClient = mock(HongguoApiClient.class);
        HongguoDramaCandidateRepository candidateRepository = mock(HongguoDramaCandidateRepository.class);
        DramaRepository dramaRepository = mock(DramaRepository.class);
        HongguoDramaService service = new HongguoDramaService(apiClient, candidateRepository, dramaRepository);
        Instant publishedAt = Instant.parse("2026-07-03T00:00:00Z");
        HongguoApiModels.MangaSearchItem first = new HongguoApiModels.MangaSearchItem(
                "anime-1",
                "热血漫剧",
                "玄幻动画故事",
                "https://example.com/anime.jpg",
                "80集",
                "8.5",
                "动漫",
                "红果短剧",
                80,
                2000L,
                null,
                List.of("动漫", "玄幻"),
                List.of("动漫热播")
        );
        HongguoApiModels.MangaSearchItem second = new HongguoApiModels.MangaSearchItem(
                "anime-2",
                "动态漫第二部",
                "修仙动画故事",
                "https://example.com/anime2.jpg",
                "80集",
                "8.3",
                "动漫",
                "红果短剧",
                80,
                1000L,
                null,
                List.of("动漫", "修仙"),
                List.of("动漫热播")
        );
        when(apiClient.searchMangaDramas("漫剧", 1))
                .thenReturn(new HongguoApiModels.MangaSearchPage("漫剧", 1, List.of(first, second)));
        when(candidateRepository.findByProviderAndProviderDramaId(HongguoDramaService.PROVIDER, "anime-1"))
                .thenReturn(Optional.empty());
        when(candidateRepository.findByProviderAndProviderDramaId(HongguoDramaService.PROVIDER, "anime-2"))
                .thenReturn(Optional.empty());
        when(apiClient.fetchDetail("anime-1", "热血漫剧")).thenReturn(new HongguoApiModels.DramaDetail(
                "anime-1",
                "热血漫剧详情",
                "详情简介",
                "https://example.com/detail-cover.jpg",
                80,
                4800,
                3000L,
                publishedAt,
                List.of(new HongguoApiModels.DetailEpisode(1, "第 1 集", "video-1", 60))
        ));
        Instant secondPublishedAt = Instant.parse("2026-07-04T00:00:00Z");
        when(apiClient.fetchDetail("anime-2", "动态漫第二部")).thenReturn(new HongguoApiModels.DramaDetail(
                "anime-2",
                "动态漫第二部详情",
                "第二部详情简介",
                "https://example.com/detail-cover-2.jpg",
                80,
                4800,
                2000L,
                secondPublishedAt,
                List.of(new HongguoApiModels.DetailEpisode(1, "第 1 集", "video-2", 60))
        ));
        when(candidateRepository.save(any(HongguoDramaCandidate.class))).thenAnswer(invocation -> invocation.getArgument(0));

        HongguoDramaService.MangaSearchResult result = service.syncMangaSearch("漫剧", 1);

        assertThat(result.fetched()).isEqualTo(2);
        assertThat(result.detailed()).isEqualTo(2);
        assertThat(result.skipped()).isZero();
        assertThat(result.created()).isEqualTo(2);
        assertThat(result.updated()).isZero();
        ArgumentCaptor<HongguoDramaCandidate> captor = ArgumentCaptor.forClass(HongguoDramaCandidate.class);
        verify(candidateRepository, times(2)).save(captor.capture());
        assertThat(captor.getAllValues())
                .extracting(HongguoDramaCandidate::getTitle)
                .containsExactly("热血漫剧详情", "动态漫第二部详情");
        assertThat(captor.getAllValues())
                .extracting(HongguoDramaCandidate::getPublishedAt)
                .containsExactly(publishedAt, secondPublishedAt);
        assertThat(captor.getAllValues())
                .extracting(HongguoDramaCandidate::getSearchKeyword)
                .containsExactly("漫剧", "漫剧");
        assertThat(captor.getAllValues())
                .extracting(HongguoDramaCandidate::getSearchPage)
                .containsExactly(1, 1);
    }

    @Test
    void syncNewDramasFetchesDetailsForAllCurrentPageCandidates() {
        HongguoApiClient apiClient = mock(HongguoApiClient.class);
        HongguoDramaCandidateRepository candidateRepository = mock(HongguoDramaCandidateRepository.class);
        DramaRepository dramaRepository = mock(DramaRepository.class);
        Instant now = Instant.parse("2026-07-07T10:00:00Z");
        Instant since = now.minus(HongguoDramaService.NEW_DRAMA_LOOKBACK);
        HongguoDramaService service = new HongguoDramaService(
                apiClient,
                candidateRepository,
                dramaRepository,
                Clock.fixed(now, ZoneOffset.UTC)
        );
        HongguoApiModels.MangaSearchItem first = new HongguoApiModels.MangaSearchItem(
                "new-1",
                "红果新剧第一部",
                "新剧简介",
                "https://example.com/new-1.jpg",
                "60集",
                "8.2",
                "都市",
                "红果短剧",
                60,
                1200L,
                since.plusSeconds(600),
                List.of("都市"),
                List.of()
        );
        HongguoApiModels.MangaSearchItem second = new HongguoApiModels.MangaSearchItem(
                "new-2",
                "红果新剧第二部",
                "第二部简介",
                "https://example.com/new-2.jpg",
                "80集",
                "8.6",
                "玄幻",
                "红果短剧",
                80,
                2400L,
                since.plusSeconds(1200),
                List.of("玄幻"),
                List.of()
        );
        when(apiClient.fetchNewDramas(2, since))
                .thenReturn(new HongguoApiModels.MangaSearchPage("红果新剧", 2, List.of(first, second)));
        when(candidateRepository.findByProviderAndProviderDramaId(HongguoDramaService.PROVIDER, "new-1"))
                .thenReturn(Optional.empty());
        when(candidateRepository.findByProviderAndProviderDramaId(HongguoDramaService.PROVIDER, "new-2"))
                .thenReturn(Optional.empty());
        Instant firstPublishedAt = Instant.parse("2026-07-05T00:00:00Z");
        Instant secondPublishedAt = Instant.parse("2026-07-06T00:00:00Z");
        when(apiClient.fetchDetail("new-1", "红果新剧第一部")).thenReturn(new HongguoApiModels.DramaDetail(
                "new-1",
                "红果新剧第一部详情",
                "新剧详情简介",
                "https://example.com/detail-new-1.jpg",
                60,
                3600,
                1500L,
                firstPublishedAt,
                List.of(new HongguoApiModels.DetailEpisode(1, "第 1 集", "video-1", 60))
        ));
        when(apiClient.fetchDetail("new-2", "红果新剧第二部")).thenReturn(new HongguoApiModels.DramaDetail(
                "new-2",
                "红果新剧第二部详情",
                "第二部详情简介",
                "https://example.com/detail-new-2.jpg",
                80,
                4800,
                3000L,
                secondPublishedAt,
                List.of(new HongguoApiModels.DetailEpisode(1, "第 1 集", "video-2", 60))
        ));
        when(candidateRepository.save(any(HongguoDramaCandidate.class))).thenAnswer(invocation -> invocation.getArgument(0));

        HongguoDramaService.MangaSearchResult result = service.syncNewDramas(2);

        assertThat(result.keyword()).isEqualTo("红果新剧");
        assertThat(result.page()).isEqualTo(2);
        assertThat(result.fetched()).isEqualTo(2);
        assertThat(result.detailed()).isEqualTo(2);
        assertThat(result.skipped()).isZero();
        assertThat(result.created()).isEqualTo(2);
        assertThat(result.updated()).isZero();
        ArgumentCaptor<HongguoDramaCandidate> captor = ArgumentCaptor.forClass(HongguoDramaCandidate.class);
        verify(candidateRepository, times(2)).save(captor.capture());
        assertThat(captor.getAllValues())
                .extracting(HongguoDramaCandidate::getTitle)
                .containsExactly("红果新剧第一部详情", "红果新剧第二部详情");
        assertThat(captor.getAllValues())
                .extracting(HongguoDramaCandidate::getPublishedAt)
                .containsExactly(firstPublishedAt, secondPublishedAt);
        assertThat(captor.getAllValues())
                .extracting(HongguoDramaCandidate::getCalendarDate)
                .containsExactly(HongguoDramaService.NEW_DRAMA_SCOPE, HongguoDramaService.NEW_DRAMA_SCOPE);
        assertThat(captor.getAllValues())
                .extracting(HongguoDramaCandidate::getCalendarPage)
                .containsExactly(2, 2);
        verify(apiClient).fetchNewDramas(2, since);
    }

    @Test
    void syncNewDramasKeepsCandidatesReturnedByApiRegardlessOfPublishedAt() {
        HongguoApiClient apiClient = mock(HongguoApiClient.class);
        HongguoDramaCandidateRepository candidateRepository = mock(HongguoDramaCandidateRepository.class);
        DramaRepository dramaRepository = mock(DramaRepository.class);
        Instant now = Instant.parse("2026-07-07T10:00:00Z");
        Instant since = now.minus(HongguoDramaService.NEW_DRAMA_LOOKBACK);
        HongguoDramaService service = new HongguoDramaService(
                apiClient,
                candidateRepository,
                dramaRepository,
                Clock.fixed(now, ZoneOffset.UTC)
        );
        HongguoApiModels.MangaSearchItem recent = new HongguoApiModels.MangaSearchItem(
                "recent",
                "近三小时新剧",
                "简介",
                "https://example.com/recent.jpg",
                "60集",
                "8.2",
                "都市",
                "红果短剧",
                60,
                1200L,
                since.plusSeconds(60),
                List.of("都市"),
                List.of()
        );
        HongguoApiModels.MangaSearchItem old = new HongguoApiModels.MangaSearchItem(
                "old",
                "三小时前旧剧",
                "简介",
                "https://example.com/old.jpg",
                "60集",
                "8.2",
                "都市",
                "红果短剧",
                60,
                1200L,
                since.minusSeconds(1),
                List.of("都市"),
                List.of()
        );
        HongguoApiModels.MangaSearchItem unknownTime = new HongguoApiModels.MangaSearchItem(
                "unknown",
                "列表未带发布时间",
                "简介",
                "https://example.com/unknown.jpg",
                "60集",
                "8.2",
                "都市",
                "红果短剧",
                60,
                1200L,
                null,
                List.of("都市"),
                List.of()
        );
        when(apiClient.fetchNewDramas(1, since))
                .thenReturn(new HongguoApiModels.MangaSearchPage("红果新剧", 1, List.of(recent, old, unknownTime)));
        when(candidateRepository.findByProviderAndProviderDramaId(HongguoDramaService.PROVIDER, "recent"))
                .thenReturn(Optional.empty());
        when(candidateRepository.findByProviderAndProviderDramaId(HongguoDramaService.PROVIDER, "old"))
                .thenReturn(Optional.empty());
        when(candidateRepository.findByProviderAndProviderDramaId(HongguoDramaService.PROVIDER, "unknown"))
                .thenReturn(Optional.empty());
        when(apiClient.fetchDetail("recent", "近三小时新剧")).thenReturn(new HongguoApiModels.DramaDetail(
                "recent",
                "近三小时新剧详情",
                "详情简介",
                "https://example.com/recent-detail.jpg",
                60,
                3600,
                1500L,
                since.plusSeconds(120),
                List.of(new HongguoApiModels.DetailEpisode(1, "第 1 集", "video-1", 60))
        ));
        when(apiClient.fetchDetail("old", "三小时前旧剧")).thenReturn(new HongguoApiModels.DramaDetail(
                "old",
                "三小时前旧剧详情",
                "详情简介",
                "https://example.com/old-detail.jpg",
                60,
                3600,
                1500L,
                since.minusSeconds(60),
                List.of(new HongguoApiModels.DetailEpisode(1, "第 1 集", "video-3", 60))
        ));
        when(apiClient.fetchDetail("unknown", "列表未带发布时间")).thenReturn(new HongguoApiModels.DramaDetail(
                "unknown",
                "列表未带发布时间详情",
                "详情简介",
                "https://example.com/unknown-detail.jpg",
                60,
                3600,
                1500L,
                since.minusSeconds(120),
                List.of(new HongguoApiModels.DetailEpisode(1, "第 1 集", "video-2", 60))
        ));
        when(candidateRepository.save(any(HongguoDramaCandidate.class))).thenAnswer(invocation -> invocation.getArgument(0));

        HongguoDramaService.MangaSearchResult result = service.syncNewDramas(1);

        assertThat(result.fetched()).isEqualTo(3);
        assertThat(result.detailed()).isEqualTo(3);
        assertThat(result.skipped()).isZero();
        assertThat(result.created()).isEqualTo(3);
        ArgumentCaptor<HongguoDramaCandidate> captor = ArgumentCaptor.forClass(HongguoDramaCandidate.class);
        verify(candidateRepository, times(3)).save(captor.capture());
        assertThat(captor.getAllValues())
                .extracting(HongguoDramaCandidate::getProviderDramaId)
                .containsExactly("recent", "old", "unknown");
    }

    @Test
    void importCandidateStoresDirectoryWithoutFetchingEpisodeDownloadUrls() {
        HongguoApiClient apiClient = mock(HongguoApiClient.class);
        HongguoDramaCandidateRepository candidateRepository = mock(HongguoDramaCandidateRepository.class);
        DramaRepository dramaRepository = mock(DramaRepository.class);
        HongguoDramaService service = new HongguoDramaService(apiClient, candidateRepository, dramaRepository);
        HongguoDramaCandidate candidate = candidate("candidate-1");
        when(candidateRepository.findById("candidate-1")).thenReturn(Optional.of(candidate));
        when(apiClient.fetchDetail("hg-1", "红果剧")).thenReturn(new HongguoApiModels.DramaDetail(
                "hg-1",
                "红果剧",
                "简介",
                "https://example.com/cover.jpg",
                2,
                360,
                100L,
                Instant.parse("2026-07-03T00:00:00Z"),
                List.of(
                        new HongguoApiModels.DetailEpisode(1, "第 1 集", "video-1", 180),
                        new HongguoApiModels.DetailEpisode(2, "第 2 集", "video-2", 180)
                )
        ));
        when(dramaRepository.findAllBySourcePath("52api://hongguo/hg-1")).thenReturn(List.of());
        when(dramaRepository.save(any(Drama.class))).thenAnswer(invocation -> {
            Drama drama = invocation.getArgument(0);
            drama.setId("drama-1");
            return drama;
        });
        when(candidateRepository.save(any(HongguoDramaCandidate.class))).thenAnswer(invocation -> invocation.getArgument(0));

        Drama drama = service.importCandidate("candidate-1");

        assertThat(drama.getSource()).isEqualTo(DramaSources.HONGGUO_52API);
        assertThat(drama.getStatus()).isEqualTo(DramaStatus.READY);
        assertThat(drama.getProviderDramaId()).isEqualTo("hg-1");
        assertThat(drama.getEpisodes()).hasSize(2);
        assertThat(drama.getEpisodes().getFirst().getProviderVideoId()).isEqualTo("video-1");
        assertThat(drama.getEpisodes().getFirst().getDownloadUrl()).isNull();
        assertThat(candidate.getStatus()).isEqualTo(HongguoCandidateStatus.IMPORTED);
        assertThat(candidate.getImportedDramaId()).isEqualTo("drama-1");
        verify(apiClient, never()).fetchVideoVariants(any(), any(), any());
        verify(apiClient, never()).decrypt(any(), any());
    }

    @Test
    void createDownloadUriReusesFreshCachedUrl() {
        HongguoApiClient apiClient = mock(HongguoApiClient.class);
        HongguoDramaService service = new HongguoDramaService(
                apiClient,
                mock(HongguoDramaCandidateRepository.class),
                mock(DramaRepository.class)
        );
        Drama drama = hongguoDrama();
        DramaEpisode episode = drama.getEpisodes().getFirst();
        episode.setDownloadUrl("https://cache.example.com/001.mp4");
        episode.setDownloadUrlExpiresAt(Instant.now().plusSeconds(600));

        URI uri = service.createDownloadUri(drama, episode);

        assertThat(uri).isEqualTo(URI.create("https://cache.example.com/001.mp4"));
        verifyNoInteractions(apiClient);
    }

    @Test
    void createDownloadUriFetchesDecryptsAndCachesWhenMissing() {
        HongguoApiClient apiClient = mock(HongguoApiClient.class);
        DramaRepository dramaRepository = mock(DramaRepository.class);
        HongguoDramaService service = new HongguoDramaService(
                apiClient,
                mock(HongguoDramaCandidateRepository.class),
                dramaRepository
        );
        Drama drama = hongguoDrama();
        DramaEpisode episode = drama.getEpisodes().getFirst();
        Instant expiresAt = Instant.now().plusSeconds(600);
        when(apiClient.fetchVideoVariants("hg-1", "红果剧", "video-1")).thenReturn(List.of(
                new HongguoApiModels.VideoVariant("https://encrypted.example.com/001.mp4", "decrypt-key", "1080p", "3分", "10 MB", 1080, 1920)
        ));
        when(apiClient.decrypt("https://encrypted.example.com/001.mp4", "decrypt-key"))
                .thenReturn(new HongguoApiModels.DecryptedUrl("https://cache.example.com/001.mp4", expiresAt));
        when(dramaRepository.save(drama)).thenReturn(drama);

        URI uri = service.createDownloadUri(drama, episode);

        assertThat(uri).isEqualTo(URI.create("https://cache.example.com/001.mp4"));
        assertThat(episode.getDownloadUrl()).isEqualTo("https://cache.example.com/001.mp4");
        assertThat(episode.getDownloadUrlExpiresAt()).isEqualTo(expiresAt);
        verify(dramaRepository).save(drama);
    }

    @Test
    void createDownloadUriTreatsEmptyVideoListAsNonRetryableDependencyFailure() {
        HongguoApiClient apiClient = mock(HongguoApiClient.class);
        DramaRepository dramaRepository = mock(DramaRepository.class);
        HongguoDramaService service = new HongguoDramaService(
                apiClient,
                mock(HongguoDramaCandidateRepository.class),
                dramaRepository
        );
        Drama drama = hongguoDrama();
        DramaEpisode episode = drama.getEpisodes().getFirst();
        when(apiClient.fetchVideoVariants("hg-1", "红果剧", "video-1")).thenReturn(List.of());

        assertThatThrownBy(() -> service.createDownloadUri(drama, episode))
                .isInstanceOfSatisfying(BusinessException.class, exception -> {
                    assertThat(exception.code()).isEqualTo("HONGGUO_VIDEO_EMPTY");
                    assertThat(exception.status()).isEqualTo(HttpStatus.FAILED_DEPENDENCY);
                });
        verify(dramaRepository, never()).save(any());
    }

    private HongguoDramaCandidate candidate(String id) {
        HongguoDramaCandidate candidate = new HongguoDramaCandidate();
        candidate.setId(id);
        candidate.setProviderDramaId("hg-1");
        candidate.setTitle("红果剧");
        candidate.setSummary("简介");
        candidate.setCategory("都市脑洞");
        candidate.setCategories(List.of("都市", "系统"));
        candidate.setEpisodeCount(2);
        return candidate;
    }

    private Drama hongguoDrama() {
        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setTitle("红果剧");
        drama.setSource(DramaSources.HONGGUO_52API);
        drama.setProviderDramaId("hg-1");
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(1);
        episode.setProviderVideoId("video-1");
        episode.setSourcePath("52api://hongguo/hg-1/video/video-1");
        drama.setEpisodes(List.of(episode));
        return drama;
    }
}
