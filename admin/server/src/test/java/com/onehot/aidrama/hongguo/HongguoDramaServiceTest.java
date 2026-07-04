package com.onehot.aidrama.hongguo;

import com.onehot.aidrama.dramas.Drama;
import com.onehot.aidrama.dramas.DramaEpisode;
import com.onehot.aidrama.dramas.DramaRepository;
import com.onehot.aidrama.dramas.DramaSources;
import com.onehot.aidrama.dramas.DramaStatus;
import org.junit.jupiter.api.Test;

import java.net.URI;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class HongguoDramaServiceTest {
    @Test
    void syncCalendarFiltersLiveActionCandidatesBeforeSaving() {
        HongguoApiClient apiClient = mock(HongguoApiClient.class);
        HongguoDramaCandidateRepository candidateRepository = mock(HongguoDramaCandidateRepository.class);
        DramaRepository dramaRepository = mock(DramaRepository.class);
        HongguoDramaService service = new HongguoDramaService(apiClient, candidateRepository, dramaRepository);
        Instant publishedAt = Instant.parse("2026-07-03T00:00:00Z");
        HongguoApiModels.CalendarItem liveAction = new HongguoApiModels.CalendarItem(
                "live-1",
                "真人都市短剧",
                "霸总甜宠故事",
                "https://example.com/live.jpg",
                "80集",
                "8.0",
                "都市",
                "红果短剧",
                80,
                1000L,
                publishedAt,
                List.of("都市", "情感"),
                List.of("300万热度")
        );
        HongguoApiModels.CalendarItem animation = new HongguoApiModels.CalendarItem(
                "anime-1",
                "热血动漫短剧",
                "玄幻动画故事",
                "https://example.com/anime.jpg",
                "80集",
                "8.5",
                "动漫",
                "红果短剧",
                80,
                2000L,
                publishedAt,
                List.of("动漫", "玄幻"),
                List.of("动漫热播")
        );
        when(apiClient.fetchCalendar(LocalDate.of(2026, 7, 3), 1))
                .thenReturn(new HongguoApiModels.CalendarPage(LocalDate.of(2026, 7, 3), 1, List.of(liveAction, animation)));
        when(candidateRepository.findByProviderAndProviderDramaId(HongguoDramaService.PROVIDER, "anime-1"))
                .thenReturn(Optional.empty());
        when(candidateRepository.save(any(HongguoDramaCandidate.class))).thenAnswer(invocation -> invocation.getArgument(0));

        HongguoDramaService.CalendarSyncResult result = service.syncCalendar(LocalDate.of(2026, 7, 3), 1);

        assertThat(result.fetched()).isEqualTo(2);
        assertThat(result.filtered()).isEqualTo(1);
        assertThat(result.created()).isEqualTo(1);
        assertThat(result.updated()).isZero();
        verify(candidateRepository, never()).findByProviderAndProviderDramaId(HongguoDramaService.PROVIDER, "live-1");
        verify(candidateRepository).save(any(HongguoDramaCandidate.class));
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
