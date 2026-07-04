package com.onehot.aidrama.dramas;

import com.onehot.aidrama.baiduyun.BaiduPanClient;
import com.onehot.aidrama.categories.DramaCategory;
import com.onehot.aidrama.categories.DramaCategoryRepository;
import com.onehot.aidrama.common.PageResult;
import com.onehot.aidrama.common.error.BusinessException;
import com.onehot.aidrama.common.security.JwtPrincipal;
import com.onehot.aidrama.distribution.DistributionTask;
import com.onehot.aidrama.distribution.DistributionTaskRepository;
import com.onehot.aidrama.distribution.DistributionTaskStatus;
import com.onehot.aidrama.hongguo.HongguoDramaService;
import com.onehot.aidrama.media.MediaAccount;
import com.onehot.aidrama.media.MediaAccountRepository;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.ArgumentCaptor;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import com.mongodb.client.result.UpdateResult;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Optional;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.mockito.Mockito.when;

class DramaControllerTest {
    private final MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
    private final DistributionTaskRepository distributionTaskRepository = mock(DistributionTaskRepository.class);
    @TempDir
    Path downloadDir;

    private DramaController controller(MongoTemplate mongoTemplate, DramaCategoryRepository categoryRepository) {
        return new DramaController(
                mock(DramaRepository.class),
                mock(BaiduPanClient.class),
                mongoTemplate,
                mock(DramaAiService.class),
                categoryRepository,
                mediaAccountRepository,
                distributionTaskRepository,
                Runnable::run,
                downloadDir
        );
    }

    private DramaController controller(MongoTemplate mongoTemplate) {
        return controller(mongoTemplate, mock(DramaCategoryRepository.class));
    }

    private DramaController controller(DramaRepository repository, BaiduPanClient baiduPanClient) {
        return controller(repository, baiduPanClient, mock(DramaAiService.class));
    }

    private DramaController controller(DramaRepository repository, BaiduPanClient baiduPanClient, DramaAiService dramaAiService) {
        return new DramaController(
                repository,
                baiduPanClient,
                mock(MongoTemplate.class),
                dramaAiService,
                mock(DramaCategoryRepository.class),
                mediaAccountRepository,
                distributionTaskRepository,
                Runnable::run,
                downloadDir
        );
    }

    private DramaController controller(
            DramaRepository repository,
            BaiduPanClient baiduPanClient,
            HongguoDramaService hongguoDramaService
    ) {
        return new DramaController(
                repository,
                baiduPanClient,
                mock(MongoTemplate.class),
                mock(DramaAiService.class),
                mock(DramaCategoryRepository.class),
                mediaAccountRepository,
                distributionTaskRepository,
                Runnable::run,
                hongguoDramaService,
                downloadDir
        );
    }

    private JwtPrincipal desktopPrincipal() {
        return new JwtPrincipal("owner-1", "test", List.of("DESKTOP_USER"));
    }

    private void mockDesktopDocuments(MongoTemplate mongoTemplate, Drama... dramas) {
        when(mongoTemplate.count(org.mockito.ArgumentMatchers.any(Query.class), eq(Drama.class))).thenReturn((long) dramas.length);
        when(mongoTemplate.find(org.mockito.ArgumentMatchers.any(Query.class), eq(Document.class), eq("dramas")))
                .thenReturn(java.util.Arrays.stream(dramas).map(this::desktopDocument).toList());
    }

    private Document desktopDocument(Drama drama) {
        return new Document("_id", drama.getId())
                .append("title", drama.getTitle())
                .append("aiTitle", drama.getAiTitle())
                .append("summary", drama.getSummary())
                .append("aiSummary", drama.getAiSummary())
                .append("coverUrl", drama.getCoverUrl())
                .append("aiCoverUrl", drama.getAiCoverUrl())
                .append("aiVideoCoverUrl", drama.getAiVideoCoverUrl())
                .append("rating", drama.getRating())
                .append("totalMinutes", drama.getTotalMinutes())
                .append("categoryIds", drama.getCategoryIds())
                .append("episodes", drama.getEpisodes() == null
                        ? List.of()
                        : drama.getEpisodes().stream()
                                .map(episode -> new Document("episodeNo", episode.getEpisodeNo()))
                                .toList())
                .append("createdAt", drama.getCreatedAt());
    }

    private DramaEpisode episode(int episodeNo) {
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(episodeNo);
        episode.setSourcePath("/短剧/%03d.mp4".formatted(episodeNo));
        return episode;
    }

    @Test
    void filtersDramasMissingCover() {
        MongoTemplate mongoTemplate = mock(MongoTemplate.class);
        DramaController controller = controller(mongoTemplate);
        when(mongoTemplate.find(org.mockito.ArgumentMatchers.any(Query.class), eq(Drama.class))).thenReturn(List.of());

        controller.list(null, null, null, DramaAssetState.MISSING_COVER, null, null, null, PageRequest.of(0, 10));

        ArgumentCaptor<Query> query = ArgumentCaptor.forClass(Query.class);
        verify(mongoTemplate).count(query.capture(), eq(Drama.class));
        assertThat(query.getValue().getQueryObject().toJson()).contains("coverUrl");
    }

    @Test
    void filtersDramasMissingSummary() {
        MongoTemplate mongoTemplate = mock(MongoTemplate.class);
        DramaController controller = controller(mongoTemplate);
        when(mongoTemplate.find(org.mockito.ArgumentMatchers.any(Query.class), eq(Drama.class))).thenReturn(List.of());

        controller.list(null, null, null, DramaAssetState.MISSING_SUMMARY, null, null, null, PageRequest.of(0, 10));

        ArgumentCaptor<Query> query = ArgumentCaptor.forClass(Query.class);
        verify(mongoTemplate).count(query.capture(), eq(Drama.class));
        assertThat(query.getValue().getQueryObject().toJson()).contains("summary");
    }

    @Test
    void filtersDramasMissingAiSummary() {
        MongoTemplate mongoTemplate = mock(MongoTemplate.class);
        DramaController controller = controller(mongoTemplate);
        when(mongoTemplate.find(org.mockito.ArgumentMatchers.any(Query.class), eq(Drama.class))).thenReturn(List.of());

        controller.list(null, null, null, DramaAssetState.MISSING_AI_SUMMARY, null, null, null, PageRequest.of(0, 10));

        ArgumentCaptor<Query> query = ArgumentCaptor.forClass(Query.class);
        verify(mongoTemplate).count(query.capture(), eq(Drama.class));
        assertThat(query.getValue().getQueryObject().toJson()).contains("aiSummary");
    }

    @Test
    void filtersDramasByEpisodeCount() {
        MongoTemplate mongoTemplate = mock(MongoTemplate.class);
        DramaController controller = controller(mongoTemplate);
        when(mongoTemplate.find(org.mockito.ArgumentMatchers.any(Query.class), eq(Drama.class))).thenReturn(List.of());

        controller.list(null, null, null, null, 50, null, null, PageRequest.of(0, 10));

        ArgumentCaptor<Query> query = ArgumentCaptor.forClass(Query.class);
        verify(mongoTemplate).count(query.capture(), eq(Drama.class));
        String queryJson = query.getValue().getQueryObject().toString();
        assertThat(queryJson).contains("episodes");
        assertThat(queryJson).contains("$size");
        assertThat(queryJson).contains("50");
    }

    @Test
    void adminListFiltersByOriginalAiTitleSummaryAiSummaryOrSourcePathKeyword() {
        MongoTemplate mongoTemplate = mock(MongoTemplate.class);
        DramaController controller = controller(mongoTemplate);
        when(mongoTemplate.find(org.mockito.ArgumentMatchers.any(Query.class), eq(Drama.class))).thenReturn(List.of());

        controller.list("山风", null, null, null, null, null, null, PageRequest.of(0, 10));

        ArgumentCaptor<Query> query = ArgumentCaptor.forClass(Query.class);
        verify(mongoTemplate).count(query.capture(), eq(Drama.class));
        String queryJson = query.getValue().getQueryObject().toString();
        assertThat(queryJson).contains("title");
        assertThat(queryJson).contains("aiTitle");
        assertThat(queryJson).contains("summary");
        assertThat(queryJson).contains("aiSummary");
        assertThat(queryJson).contains("sourcePath");
        assertThat(queryJson).contains("山风");
    }

    @Test
    void adminListDefaultsToCreatedAtDescending() {
        MongoTemplate mongoTemplate = mock(MongoTemplate.class);
        DramaController controller = controller(mongoTemplate);
        when(mongoTemplate.find(org.mockito.ArgumentMatchers.any(Query.class), eq(Drama.class))).thenReturn(List.of());

        controller.list(null, null, null, null, null, null, null, PageRequest.of(0, 10));

        ArgumentCaptor<Query> query = ArgumentCaptor.forClass(Query.class);
        verify(mongoTemplate).find(query.capture(), eq(Drama.class));
        assertThat(query.getValue().getSortObject().toString()).contains("createdAt=-1");
    }

    @Test
    void adminListPreservesRequestedSort() {
        MongoTemplate mongoTemplate = mock(MongoTemplate.class);
        DramaController controller = controller(mongoTemplate);
        when(mongoTemplate.find(org.mockito.ArgumentMatchers.any(Query.class), eq(Drama.class))).thenReturn(List.of());

        controller.list(null, null, null, null, null, null, null, PageRequest.of(0, 10, Sort.by("title").ascending()));

        ArgumentCaptor<Query> query = ArgumentCaptor.forClass(Query.class);
        verify(mongoTemplate).find(query.capture(), eq(Drama.class));
        assertThat(query.getValue().getSortObject().toString()).contains("title=1");
        assertThat(query.getValue().getSortObject().toString()).doesNotContain("createdAt");
    }

    @Test
    void ignoresNonPositiveEpisodeCountFilter() {
        MongoTemplate mongoTemplate = mock(MongoTemplate.class);
        DramaController controller = controller(mongoTemplate);
        when(mongoTemplate.find(org.mockito.ArgumentMatchers.any(Query.class), eq(Drama.class))).thenReturn(List.of());

        controller.list(null, null, null, null, 0, null, null, PageRequest.of(0, 10));

        ArgumentCaptor<Query> query = ArgumentCaptor.forClass(Query.class);
        verify(mongoTemplate).count(query.capture(), eq(Drama.class));
        assertThat(query.getValue().getQueryObject().toJson()).doesNotContain("$size");
    }

    @Test
    void desktopListReturnsReadyDramasUpdatedInLastSevenDaysWithoutRequiringAiAssets() {
        MongoTemplate mongoTemplate = mock(MongoTemplate.class);
        DramaController controller = controller(mongoTemplate);
        when(mongoTemplate.find(org.mockito.ArgumentMatchers.any(Query.class), eq(Document.class), eq("dramas"))).thenReturn(List.of());

        controller.desktopList(desktopPrincipal(), null, PageRequest.of(0, 10));

        ArgumentCaptor<Query> query = ArgumentCaptor.forClass(Query.class);
        verify(mongoTemplate).count(query.capture(), eq(Drama.class));
        String queryJson = query.getValue().getQueryObject().toString();
        assertThat(queryJson).contains("status=READY");
        assertThat(queryJson).contains("updatedAt");
        assertThat(queryJson).contains("$gte");
        assertThat(queryJson).doesNotContain("aiTitle");
        assertThat(queryJson).doesNotContain("aiSummary");
        assertThat(queryJson).doesNotContain("aiCoverUrl");
    }

    @Test
    void desktopListSortsByUpdatedAtDescending() {
        MongoTemplate mongoTemplate = mock(MongoTemplate.class);
        DramaController controller = controller(mongoTemplate);
        when(mongoTemplate.find(org.mockito.ArgumentMatchers.any(Query.class), eq(Document.class), eq("dramas"))).thenReturn(List.of());

        controller.desktopList(desktopPrincipal(), null, PageRequest.of(0, 10));

        ArgumentCaptor<Query> query = ArgumentCaptor.forClass(Query.class);
        verify(mongoTemplate).find(query.capture(), eq(Document.class), eq("dramas"));
        assertThat(query.getValue().getSortObject().toString()).contains("updatedAt=-1");
    }

    @Test
    void batchFreshUpdatesSelectedDramaUpdatedAt() {
        MongoTemplate mongoTemplate = mock(MongoTemplate.class);
        DramaController controller = controller(mongoTemplate);
        when(mongoTemplate.updateMulti(
                org.mockito.ArgumentMatchers.any(Query.class),
                org.mockito.ArgumentMatchers.any(Update.class),
                eq(Drama.class)
        )).thenReturn(UpdateResult.acknowledged(2, 2L, null));

        DramaDtos.BatchFreshResponse response = controller.batchFresh(
                new DramaDtos.BatchIdsRequest(List.of("drama-1", "drama-2"))
        ).data();

        ArgumentCaptor<Query> query = ArgumentCaptor.forClass(Query.class);
        ArgumentCaptor<Update> update = ArgumentCaptor.forClass(Update.class);
        verify(mongoTemplate).updateMulti(query.capture(), update.capture(), eq(Drama.class));
        assertThat(query.getValue().getQueryObject().toString()).contains("drama-1", "drama-2");
        assertThat(update.getValue().getUpdateObject().toString()).contains("updatedAt");
        assertThat(response.requested()).isEqualTo(2);
        assertThat(response.updated()).isEqualTo(2);
    }

    @Test
    void desktopListFiltersByOriginalAiTitleOrAiSummaryKeyword() {
        MongoTemplate mongoTemplate = mock(MongoTemplate.class);
        DramaController controller = controller(mongoTemplate);
        when(mongoTemplate.find(org.mockito.ArgumentMatchers.any(Query.class), eq(Document.class), eq("dramas"))).thenReturn(List.of());

        controller.desktopList(desktopPrincipal(), "神医", PageRequest.of(0, 10));

        ArgumentCaptor<Query> query = ArgumentCaptor.forClass(Query.class);
        verify(mongoTemplate).count(query.capture(), eq(Drama.class));
        String queryJson = query.getValue().getQueryObject().toString();
        assertThat(queryJson).contains("title");
        assertThat(queryJson).contains("aiTitle");
        assertThat(queryJson).contains("aiSummary");
        assertThat(queryJson).contains("神医");
    }

    @Test
    void desktopListReturnsCategoryNames() {
        MongoTemplate mongoTemplate = mock(MongoTemplate.class);
        DramaCategoryRepository categoryRepository = mock(DramaCategoryRepository.class);
        DramaController controller = controller(mongoTemplate, categoryRepository);
        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setTitle("短剧");
        drama.setCategoryIds(List.of("sci-fi"));
        DramaCategory category = new DramaCategory();
        category.setCode("sci-fi");
        category.setName("科幻");
        mockDesktopDocuments(mongoTemplate, drama);
        when(categoryRepository.findByEnabledTrueOrderBySortOrderAsc()).thenReturn(List.of(category));

        PageResult<DramaDtos.DesktopDramaResponse> result = controller.desktopList(desktopPrincipal(), null, PageRequest.of(0, 10)).data();

        assertThat(result.content()).hasSize(1);
        assertThat(result.content().getFirst().categoryNames()).containsExactly("科幻");
    }

    @Test
    void desktopListReturnsEpisodeCountWithoutEpisodeDetails() {
        MongoTemplate mongoTemplate = mock(MongoTemplate.class);
        DramaController controller = controller(mongoTemplate);
        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setTitle("短剧");
        DramaEpisode first = new DramaEpisode();
        first.setEpisodeNo(1);
        first.setSourcePath("/短剧/001.mp4");
        DramaEpisode second = new DramaEpisode();
        second.setEpisodeNo(2);
        second.setSourcePath("/短剧/002.mp4");
        drama.setEpisodes(List.of(first, second));
        mockDesktopDocuments(mongoTemplate, drama);

        DramaDtos.DesktopDramaResponse row = controller.desktopList(desktopPrincipal(), null, PageRequest.of(0, 10)).data().content().getFirst();

        assertThat(row.episodeCount()).isEqualTo(2);
        assertThat(DramaDtos.DesktopDramaResponse.class.getRecordComponents())
                .extracting(java.lang.reflect.RecordComponent::getName)
                .doesNotContain("episodes");
    }

    @Test
    void desktopListReturnsTotalMinutes() {
        MongoTemplate mongoTemplate = mock(MongoTemplate.class);
        DramaController controller = controller(mongoTemplate);
        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setTitle("短剧");
        drama.setTotalMinutes(123);
        mockDesktopDocuments(mongoTemplate, drama);

        DramaDtos.DesktopDramaResponse row = controller.desktopList(desktopPrincipal(), null, PageRequest.of(0, 10)).data().content().getFirst();

        assertThat(row.totalMinutes()).isEqualTo(123);
    }

    @Test
    void backfillTotalMinutesUpdatesSelectedMissingAndNonRoundedValues() {
        DramaRepository repository = mock(DramaRepository.class);
        DramaController controller = controller(repository, mock(BaiduPanClient.class));
        Drama missing = new Drama();
        missing.setId("missing");
        missing.setTitle("缺失时长");
        missing.setEpisodes(List.of(episode(1), episode(2)));
        Drama existing = new Drama();
        existing.setId("existing");
        existing.setTitle("已有时长");
        existing.setEpisodes(List.of(episode(1)));
        existing.setTotalMinutes(120);
        Drama nonRounded = new Drama();
        nonRounded.setId("non-rounded");
        nonRounded.setTitle("非整十时长");
        nonRounded.setEpisodes(List.of(episode(1), episode(2), episode(3)));
        nonRounded.setTotalMinutes(121);
        when(repository.findAllById(List.of("missing", "existing"))).thenReturn(List.of(missing, existing));
        when(repository.save(org.mockito.ArgumentMatchers.any(Drama.class))).thenAnswer(invocation -> invocation.getArgument(0));

        DramaDtos.BackfillTotalMinutesResponse response = controller.backfillTotalMinutes(
                new DramaDtos.BatchIdsRequest(List.of("missing", "existing"))
        ).data();

        assertThat(response.requested()).isEqualTo(2);
        assertThat(response.updated()).isEqualTo(1);
        assertThat(missing.getTotalMinutes()).isEqualTo(10);
        assertThat(existing.getTotalMinutes()).isEqualTo(120);
        assertThat(nonRounded.getTotalMinutes()).isEqualTo(121);
        verify(repository).save(missing);
        verify(repository, never()).save(nonRounded);
        verify(repository, never()).findAll();
    }

    @Test
    void backfillTotalMinutesDoesNothingWithoutSelectedIds() {
        DramaRepository repository = mock(DramaRepository.class);
        DramaController controller = controller(repository, mock(BaiduPanClient.class));

        DramaDtos.BackfillTotalMinutesResponse response = controller.backfillTotalMinutes(
                new DramaDtos.BatchIdsRequest(List.of())
        ).data();

        assertThat(response.requested()).isZero();
        assertThat(response.updated()).isZero();
        verify(repository, never()).findAllById(org.mockito.ArgumentMatchers.any());
    }

    @Test
    void backfillAiSummariesSubmitsOnlySelectedDramaIds() {
        DramaRepository repository = mock(DramaRepository.class);
        DramaAiService dramaAiService = mock(DramaAiService.class);
        DramaController controller = controller(repository, mock(BaiduPanClient.class), dramaAiService);
        Drama first = new Drama();
        first.setId("drama-1");
        Drama second = new Drama();
        second.setId("drama-2");
        when(repository.findAllById(List.of("drama-1", "drama-2"))).thenReturn(List.of(first, second));

        DramaDtos.BackfillAiSummariesAccepted response = controller.backfillAiSummaries(
                new DramaDtos.BatchIdsRequest(List.of("drama-1", "", "drama-2", "drama-1"))
        ).data();

        assertThat(response.requested()).isEqualTo(2);
        verify(repository).findAllById(List.of("drama-1", "drama-2"));
        verify(dramaAiService).generateSummary("drama-1");
        verify(dramaAiService).generateSummary("drama-2");
        verify(dramaAiService, never()).generateSummary("drama-3");
    }

    @Test
    void desktopListUsesProjectedDocumentsInsteadOfFullDramaDocuments() {
        MongoTemplate mongoTemplate = mock(MongoTemplate.class);
        DramaController controller = controller(mongoTemplate);
        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setTitle("短剧");
        mockDesktopDocuments(mongoTemplate, drama);

        controller.desktopList(desktopPrincipal(), null, PageRequest.of(0, 10));

        ArgumentCaptor<Query> projectedQuery = ArgumentCaptor.forClass(Query.class);
        verify(mongoTemplate).find(projectedQuery.capture(), eq(Document.class), eq("dramas"));
        verify(mongoTemplate, never()).find(org.mockito.ArgumentMatchers.any(Query.class), eq(Drama.class));
        assertThat(projectedQuery.getValue().getFieldsObject().get("episodes.episodeNo")).isEqualTo(1);
        assertThat(projectedQuery.getValue().getFieldsObject()).doesNotContainKeys("episodes.sourcePath", "episodes.size");
    }

    @Test
    void desktopListReplacesOriginalTitleAndCoverWithAiValues() {
        MongoTemplate mongoTemplate = mock(MongoTemplate.class);
        DramaController controller = controller(mongoTemplate);
        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setTitle("原始剧名");
        drama.setAiTitle("AI剧名");
        drama.setCoverUrl("/uploads/covers/original.jpg");
        drama.setAiCoverUrl("/uploads/ai-covers/ai.jpg");
        drama.setAiVideoCoverUrl("/uploads/ai-covers/video.jpg");
        mockDesktopDocuments(mongoTemplate, drama);

        DramaDtos.DesktopDramaResponse row = controller.desktopList(desktopPrincipal(), null, PageRequest.of(0, 10)).data().content().getFirst();

        assertThat(row.title()).isEqualTo("AI剧名");
        assertThat(row.coverUrl()).isEqualTo("/uploads/ai-covers/ai.jpg");
        assertThat(row.aiTitle()).isNull();
        assertThat(row.aiCoverUrl()).isNull();
        assertThat(row.aiVideoCoverUrl()).isEqualTo("/uploads/ai-covers/video.jpg");
    }

    @Test
    void desktopListMarksPrioritizedDramasForCurrentOwner() {
        MongoTemplate mongoTemplate = mock(MongoTemplate.class);
        DramaController controller = controller(mongoTemplate);
        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setTitle("短剧");
        MediaAccount media = new MediaAccount();
        media.setId("media-1");
        DistributionTask task = new DistributionTask();
        task.setDramaId("drama-1");
        task.setMediaAccountId("media-1");
        task.setStatus(DistributionTaskStatus.PENDING);
        task.setPriority(100);
        mockDesktopDocuments(mongoTemplate, drama);
        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(media));
        when(distributionTaskRepository.findByStatusAndPriorityGreaterThanAndMediaAccountIdIn(
                DistributionTaskStatus.PENDING,
                0,
                List.of("media-1")
        )).thenReturn(List.of(task));

        PageResult<DramaDtos.DesktopDramaResponse> result = controller.desktopList(desktopPrincipal(), null, PageRequest.of(0, 10)).data();

        assertThat(result.content().getFirst().prioritized()).isTrue();
    }

    @Test
    void generateCoverAcceptsRequestAndRunsGenerationInBackground() {
        DramaRepository repository = mock(DramaRepository.class);
        DramaAiService dramaAiService = mock(DramaAiService.class);
        AtomicReference<Runnable> backgroundTask = new AtomicReference<>();
        DramaController controller = new DramaController(
                repository,
                mock(BaiduPanClient.class),
                mock(MongoTemplate.class),
                dramaAiService,
                mock(DramaCategoryRepository.class),
                mediaAccountRepository,
                distributionTaskRepository,
                backgroundTask::set
        );
        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setAiCoverUrl("/uploads/ai-covers/new.jpg");
        when(repository.findById("drama-1")).thenReturn(Optional.of(drama));
        when(repository.save(org.mockito.ArgumentMatchers.any(Drama.class))).thenAnswer(invocation -> invocation.getArgument(0));
        when(dramaAiService.generateCover("drama-1")).thenReturn(drama);

        var response = controller.generateCover("drama-1");

        assertThat(response.data().dramaId()).isEqualTo("drama-1");
        assertThat(response.data().acceptedAt()).isNotNull();
        assertThat(response.data().recommendedCheckAt()).isAfter(response.data().acceptedAt());
        assertThat(drama.isAiCoverGenerating()).isTrue();
        verifyNoInteractions(dramaAiService);

        backgroundTask.get().run();

        verify(dramaAiService).generateCover("drama-1");
    }

    @Test
    void updateAllowsReadyStatusBeforeAiTitleAndCoverAreGenerated() {
        DramaRepository repository = mock(DramaRepository.class);
        DramaController controller = controller(repository, mock(BaiduPanClient.class));
        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setTitle("原始剧名");
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(1);
        episode.setSourcePath("/短剧/001.mp4");
        drama.setEpisodes(List.of(episode));
        when(repository.findById("drama-1")).thenReturn(Optional.of(drama));

        DramaDtos.DramaRequest request = new DramaDtos.DramaRequest(
                "原始剧名",
                "",
                "简介",
                "",
                "/uploads/covers/source.jpg",
                "",
                "",
                5,
                3,
                List.of("urban"),
                DramaStatus.READY
        );
        when(repository.save(org.mockito.ArgumentMatchers.any(Drama.class))).thenAnswer(invocation -> invocation.getArgument(0));

        Drama updated = controller.update("drama-1", request).data();

        assertThat(updated.getStatus()).isEqualTo(DramaStatus.READY);
        verify(repository).save(drama);
    }

    @Test
    void deleteRemovesExistingDrama() {
        DramaRepository repository = mock(DramaRepository.class);
        DramaController controller = controller(repository, mock(BaiduPanClient.class));
        Drama drama = new Drama();
        drama.setId("drama-1");
        when(repository.findById("drama-1")).thenReturn(Optional.of(drama));

        controller.delete("drama-1");

        verify(repository).delete(drama);
    }

    @Test
    void deleteRejectsMissingDrama() {
        DramaRepository repository = mock(DramaRepository.class);
        DramaController controller = controller(repository, mock(BaiduPanClient.class));
        when(repository.findById("missing")).thenReturn(Optional.empty());

        assertThatThrownBy(() -> controller.delete("missing"))
                .isInstanceOf(BusinessException.class)
                .hasMessage("短剧不存在");
        verify(repository).findById("missing");
        verifyNoMoreInteractions(repository);
    }

    @Test
    void desktopListReturnsDefaultRatingForLegacyDramas() {
        MongoTemplate mongoTemplate = mock(MongoTemplate.class);
        DramaController controller = controller(mongoTemplate);
        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setTitle("短剧");
        mockDesktopDocuments(mongoTemplate, drama);

        PageResult<DramaDtos.DesktopDramaResponse> result = controller.desktopList(desktopPrincipal(), null, PageRequest.of(0, 10)).data();

        assertThat(result.content().getFirst().rating()).isEqualTo(5);
    }

    @Test
    void downloadPlanReturnsBackendEpisodeUrlsWithoutCreatingBaiduLinks() {
        DramaRepository repository = mock(DramaRepository.class);
        BaiduPanClient baiduPanClient = mock(BaiduPanClient.class);
        DramaController controller = controller(repository, baiduPanClient);
        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setTitle("短剧");
        drama.setAiTitle("AI短剧名");
        drama.setSummary("简介");
        drama.setAiSummary("AI简介...");
        drama.setCoverUrl("/uploads/covers/source.jpg");
        drama.setAiCoverUrl("/uploads/ai-covers/ai.jpg");
        drama.setAiVideoCoverUrl("/uploads/ai-covers/video.jpg");
        drama.setCategoryIds(List.of("urban"));
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(1);
        episode.setSourcePath("/短剧/001.mp4");
        episode.setSize(12345);
        drama.setEpisodes(List.of(episode));
        when(repository.findById("drama-1")).thenReturn(Optional.of(drama));

        DramaDtos.DownloadPlan plan = controller.downloadPlan("drama-1").data();

        assertThat(plan.episodes()).hasSize(1);
        assertThat(plan.title()).isEqualTo("AI短剧名");
        assertThat(plan.aiTitle()).isEqualTo("AI短剧名");
        assertThat(plan.summary()).isEqualTo("简介");
        assertThat(plan.aiSummary()).isEqualTo("AI简介...");
        assertThat(plan.coverUrl()).isEqualTo("/uploads/covers/source.jpg");
        assertThat(plan.aiCoverUrl()).isEqualTo("/uploads/ai-covers/ai.jpg");
        assertThat(plan.aiVideoCoverUrl()).isEqualTo("/uploads/ai-covers/video.jpg");
        assertThat(plan.effectiveCoverUrl()).isEqualTo("/uploads/ai-covers/ai.jpg");
        assertThat(plan.categoryIds()).containsExactly("urban");
        assertThat(plan.episodes().getFirst().size()).isEqualTo(12345);
        assertThat(plan.episodes().getFirst().downloadUrl())
                .isEqualTo("/api/desktop/dramas/drama-1/episodes/1/download");
        verifyNoInteractions(baiduPanClient);
    }

    @Test
    void downloadEpisodeRedirectsToFreshBaiduUrl() {
        DramaRepository repository = mock(DramaRepository.class);
        BaiduPanClient baiduPanClient = mock(BaiduPanClient.class);
        DramaController controller = controller(repository, baiduPanClient);
        Drama drama = new Drama();
        drama.setId("drama-1");
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(2);
        episode.setSourcePath("/短剧/002.mp4");
        drama.setEpisodes(List.of(episode));
        when(repository.findById("drama-1")).thenReturn(Optional.of(drama));
        when(baiduPanClient.createDownloadUrls(List.of("/短剧/002.mp4")))
                .thenReturn(List.of("https://pan.baidu.com/download?token=secret"));

        var response = controller.downloadEpisode("drama-1", 2);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.FOUND);
        assertThat(response.getHeaders().getLocation().toString())
                .isEqualTo("https://pan.baidu.com/download?token=secret");
    }

    @Test
    void adminEpisodesShowDownloadedStateFromLocalFiles() throws Exception {
        DramaRepository repository = mock(DramaRepository.class);
        DramaController controller = controller(repository, mock(BaiduPanClient.class));
        Drama drama = new Drama();
        drama.setId("drama-1");
        DramaEpisode first = new DramaEpisode();
        first.setEpisodeNo(1);
        first.setTitle("第一集");
        first.setSourcePath("/短剧/001.mp4");
        first.setSize(100);
        DramaEpisode second = new DramaEpisode();
        second.setEpisodeNo(2);
        second.setTitle("第二集");
        second.setSourcePath("/短剧/002.mp4");
        second.setSize(200);
        drama.setEpisodes(List.of(first, second));
        when(repository.findById("drama-1")).thenReturn(Optional.of(drama));
        Path localFile = downloadDir.resolve("drama-1").resolve("001.mp4");
        Files.createDirectories(localFile.getParent());
        Files.writeString(localFile, "video");

        var episodes = controller.adminEpisodes("drama-1").data();

        assertThat(episodes).hasSize(2);
        assertThat(episodes.getFirst().downloaded()).isTrue();
        assertThat(episodes.getFirst().playSource()).isEqualTo("LOCAL");
        assertThat(episodes.getFirst().localUrl()).isEqualTo("/api/admin/dramas/drama-1/episodes/1/stream");
        assertThat(episodes.get(1).downloaded()).isFalse();
        assertThat(episodes.get(1).playSource()).isEqualTo("BAIDU");
    }

    @Test
    void adminEpisodePlaySourcePrefersLocalFileOverBaiduUrl() throws Exception {
        DramaRepository repository = mock(DramaRepository.class);
        BaiduPanClient baiduPanClient = mock(BaiduPanClient.class);
        DramaController controller = controller(repository, baiduPanClient);
        Drama drama = new Drama();
        drama.setId("drama-1");
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(1);
        episode.setSourcePath("/短剧/001.mp4");
        drama.setEpisodes(List.of(episode));
        when(repository.findById("drama-1")).thenReturn(Optional.of(drama));
        Path localFile = downloadDir.resolve("drama-1").resolve("001.mp4");
        Files.createDirectories(localFile.getParent());
        Files.writeString(localFile, "video");

        DramaDtos.EpisodePlaySource source = controller.adminEpisodePlaySource("drama-1", 1).data();

        assertThat(source.source()).isEqualTo("LOCAL");
        assertThat(source.downloaded()).isTrue();
        assertThat(source.playUrl()).isEqualTo("/api/admin/dramas/drama-1/episodes/1/stream");
        verifyNoInteractions(baiduPanClient);
    }

    @Test
    void adminEpisodePlaySourceFallsBackToProxiedBaiduHlsUrl() {
        DramaRepository repository = mock(DramaRepository.class);
        BaiduPanClient baiduPanClient = mock(BaiduPanClient.class);
        DramaController controller = controller(repository, baiduPanClient);
        Drama drama = new Drama();
        drama.setId("drama-1");
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(2);
        episode.setSourcePath("/短剧/002.mp4");
        drama.setEpisodes(List.of(episode));
        when(repository.findById("drama-1")).thenReturn(Optional.of(drama));

        DramaDtos.EpisodePlaySource source = controller.adminEpisodePlaySource("drama-1", 2).data();

        assertThat(source.source()).isEqualTo("BAIDU");
        assertThat(source.downloaded()).isFalse();
        assertThat(source.playUrl()).isEqualTo("/api/admin/dramas/drama-1/episodes/2/hls.m3u8");
        verifyNoInteractions(baiduPanClient);
    }

    @Test
    void adminEpisodePlaySourceUsesHongguoStreamUrlWithoutBaiduHls() {
        DramaRepository repository = mock(DramaRepository.class);
        BaiduPanClient baiduPanClient = mock(BaiduPanClient.class);
        HongguoDramaService hongguoDramaService = mock(HongguoDramaService.class);
        DramaController controller = controller(repository, baiduPanClient, hongguoDramaService);
        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setSource(DramaSources.HONGGUO_52API);
        drama.setProviderDramaId("hg-1");
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(2);
        episode.setProviderVideoId("video-2");
        episode.setSourcePath("52api://hongguo/hg-1/video/video-2");
        drama.setEpisodes(List.of(episode));
        when(repository.findById("drama-1")).thenReturn(Optional.of(drama));

        DramaDtos.EpisodePlaySource source = controller.adminEpisodePlaySource("drama-1", 2).data();

        assertThat(source.source()).isEqualTo("HONGGUO");
        assertThat(source.downloaded()).isFalse();
        assertThat(source.playUrl()).isEqualTo("/api/admin/dramas/drama-1/episodes/2/stream");
        verifyNoInteractions(baiduPanClient, hongguoDramaService);
    }

    @Test
    void desktopDownloadEpisodeRedirectsToHongguoUriWithoutBaiduLinks() {
        DramaRepository repository = mock(DramaRepository.class);
        BaiduPanClient baiduPanClient = mock(BaiduPanClient.class);
        HongguoDramaService hongguoDramaService = mock(HongguoDramaService.class);
        DramaController controller = controller(repository, baiduPanClient, hongguoDramaService);
        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setSource(DramaSources.HONGGUO_52API);
        drama.setProviderDramaId("hg-1");
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(2);
        episode.setProviderVideoId("video-2");
        episode.setSourcePath("52api://hongguo/hg-1/video/video-2");
        drama.setEpisodes(List.of(episode));
        when(repository.findById("drama-1")).thenReturn(Optional.of(drama));
        when(hongguoDramaService.createDownloadUri(drama, episode))
                .thenReturn(java.net.URI.create("https://video.example.com/002.mp4"));

        var response = controller.downloadEpisode("drama-1", 2);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.FOUND);
        assertThat(response.getHeaders().getLocation().toString())
                .isEqualTo("https://video.example.com/002.mp4");
        verify(hongguoDramaService).createDownloadUri(drama, episode);
        verifyNoInteractions(baiduPanClient);
    }

    @Test
    void baiduHlsManifestRewritesSegmentsToSameOriginUrls() {
        DramaRepository repository = mock(DramaRepository.class);
        BaiduPanClient baiduPanClient = mock(BaiduPanClient.class);
        DramaController controller = controller(repository, baiduPanClient);
        Drama drama = new Drama();
        drama.setId("drama-1");
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(2);
        episode.setSourcePath("/短剧/002.mp4");
        drama.setEpisodes(List.of(episode));
        when(repository.findById("drama-1")).thenReturn(Optional.of(drama));
        when(baiduPanClient.createStreamingUrl("/短剧/002.mp4"))
                .thenReturn("https://pan.baidu.com/rest/2.0/xpan/file?method=streaming&type=M3U8_AUTO_720&token=secret");
        String segmentUrl = "https://v2-ant.baidu.com/video/segment.ts?range=0-100&sign=abc";
        when(baiduPanClient.readUrl("https://pan.baidu.com/rest/2.0/xpan/file?method=streaming&type=M3U8_AUTO_720&token=secret"))
                .thenReturn("#EXTM3U\n#EXTINF:2,\n" + segmentUrl + "\n#EXT-X-ENDLIST\n");

        var response = controller.baiduHlsManifest("drama-1", 2);

        assertThat(response.getHeaders().getContentType().toString()).isEqualTo("application/vnd.apple.mpegurl");
        assertThat(response.getBody()).contains("/api/admin/dramas/drama-1/episodes/2/hls-segment?url=");
        assertThat(response.getBody()).doesNotContain(segmentUrl);
        String encoded = response.getBody().lines()
                .filter(line -> line.contains("/hls-segment?url="))
                .findFirst()
                .orElseThrow()
                .substring("/api/admin/dramas/drama-1/episodes/2/hls-segment?url=".length());
        assertThat(new String(Base64.getUrlDecoder().decode(encoded), StandardCharsets.UTF_8)).isEqualTo(segmentUrl);
    }

    @Test
    void baiduHlsSegmentDownloadsOnlyBaiduUrls() {
        DramaRepository repository = mock(DramaRepository.class);
        BaiduPanClient baiduPanClient = mock(BaiduPanClient.class);
        DramaController controller = controller(repository, baiduPanClient);
        Drama drama = new Drama();
        drama.setId("drama-1");
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(2);
        episode.setSourcePath("/短剧/002.mp4");
        drama.setEpisodes(List.of(episode));
        when(repository.findById("drama-1")).thenReturn(Optional.of(drama));
        String segmentUrl = "https://v2-ant.baidu.com/video/segment.ts?range=0-100&sign=abc";
        String encoded = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(segmentUrl.getBytes(StandardCharsets.UTF_8));
        when(baiduPanClient.downloadUrl(segmentUrl)).thenReturn(new byte[]{1, 2, 3});

        var response = controller.baiduHlsSegment("drama-1", 2, encoded);

        assertThat(response.getBody()).containsExactly(1, 2, 3);
        assertThat(response.getHeaders().getContentType()).isEqualTo(org.springframework.http.MediaType.APPLICATION_OCTET_STREAM);
        verify(baiduPanClient).downloadUrl(segmentUrl);
    }

    @Test
    void baiduHlsSegmentRejectsNonBaiduUrls() {
        DramaRepository repository = mock(DramaRepository.class);
        BaiduPanClient baiduPanClient = mock(BaiduPanClient.class);
        DramaController controller = controller(repository, baiduPanClient);
        Drama drama = new Drama();
        drama.setId("drama-1");
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(2);
        episode.setSourcePath("/短剧/002.mp4");
        drama.setEpisodes(List.of(episode));
        when(repository.findById("drama-1")).thenReturn(Optional.of(drama));
        String encoded = Base64.getUrlEncoder().withoutPadding()
                .encodeToString("https://example.com/segment.ts".getBytes(StandardCharsets.UTF_8));

        assertThatThrownBy(() -> controller.baiduHlsSegment("drama-1", 2, encoded))
                .isInstanceOf(BusinessException.class)
                .hasMessage("非法的百度分片地址");
        verify(baiduPanClient, never()).downloadUrl(org.mockito.ArgumentMatchers.anyString());
    }

    @Test
    void streamAdminEpisodeDownloadsAndServesFileWhenLocalFileMissing() throws Exception {
        DramaRepository repository = mock(DramaRepository.class);
        BaiduPanClient baiduPanClient = mock(BaiduPanClient.class);
        DramaController controller = controller(repository, baiduPanClient);
        Drama drama = new Drama();
        drama.setId("drama-1");
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(2);
        episode.setSourcePath("/短剧/002.mp4");
        drama.setEpisodes(List.of(episode));
        when(repository.findById("drama-1")).thenReturn(Optional.of(drama));
        doAnswer(invocation -> {
            Path target = invocation.getArgument(1);
            Files.createDirectories(target.getParent());
            Files.writeString(target, "video");
            return null;
        }).when(baiduPanClient).downloadFile(eq("/短剧/002.mp4"), org.mockito.ArgumentMatchers.any(Path.class));

        var response = controller.streamAdminEpisode("drama-1", 2, null);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getHeaders().getContentLength()).isEqualTo(5);
        assertThat(Files.readString(downloadDir.resolve("drama-1").resolve("002.mp4"))).isEqualTo("video");
        verify(baiduPanClient).downloadFile(eq("/短剧/002.mp4"), org.mockito.ArgumentMatchers.any(Path.class));
    }

    @Test
    void streamAdminEpisodeDownloadsHongguoFileWithoutBaiduClient() throws Exception {
        DramaRepository repository = mock(DramaRepository.class);
        BaiduPanClient baiduPanClient = mock(BaiduPanClient.class);
        HongguoDramaService hongguoDramaService = mock(HongguoDramaService.class);
        DramaController controller = controller(repository, baiduPanClient, hongguoDramaService);
        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setSource(DramaSources.HONGGUO_52API);
        drama.setProviderDramaId("hg-1");
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(2);
        episode.setProviderVideoId("video-2");
        episode.setSourcePath("52api://hongguo/hg-1/video/video-2");
        drama.setEpisodes(List.of(episode));
        when(repository.findById("drama-1")).thenReturn(Optional.of(drama));
        doAnswer(invocation -> {
            Path target = invocation.getArgument(2);
            Files.createDirectories(target.getParent());
            Files.writeString(target, "video");
            return null;
        }).when(hongguoDramaService).downloadEpisodeToFile(eq(drama), eq(episode), org.mockito.ArgumentMatchers.any(Path.class));

        var response = controller.streamAdminEpisode("drama-1", 2, null);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getHeaders().getContentLength()).isEqualTo(5);
        assertThat(Files.readString(downloadDir.resolve("drama-1").resolve("002.mp4"))).isEqualTo("video");
        verify(hongguoDramaService).downloadEpisodeToFile(eq(drama), eq(episode), org.mockito.ArgumentMatchers.any(Path.class));
        verifyNoInteractions(baiduPanClient);
    }
}
