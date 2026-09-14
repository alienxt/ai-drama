package com.onehot.aidrama.baiduyun;

import com.onehot.aidrama.system.SystemTask;
import com.onehot.aidrama.system.SystemTaskRepository;
import com.onehot.aidrama.system.SystemTaskService;
import com.onehot.aidrama.system.SystemTaskStatus;
import com.onehot.aidrama.system.SystemTaskType;
import org.junit.jupiter.api.Test;
import org.springframework.core.task.TaskExecutor;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class BaiduScanControllerTest {
    @Test
    void acceptsBaiduScanWithoutRunningScannerOnRequestThread() {
        BaiduDramaScanner scanner = mock(BaiduDramaScanner.class);
        List<Runnable> backgroundTasks = new ArrayList<>();
        BaiduScanController controller = controller(scanner, backgroundTasks::add);
        com.onehot.aidrama.dramas.Drama drama = new com.onehot.aidrama.dramas.Drama();
        drama.setId("drama-1");
        when(scanner.scanLatestConfiguredRoot()).thenReturn(List.of(drama));

        var response = controller.scan(new BaiduScanController.ScanRequest(null));

        assertThat(response.data().acceptedAt()).isNotNull();
        verify(scanner, never()).scanLatestConfiguredRoot();

        backgroundTasks.getFirst().run();

        verify(scanner).scanLatestConfiguredRoot();
    }

    @Test
    void acceptsAssetSyncWithoutRunningScannerOnRequestThread() {
        BaiduDramaScanner scanner = mock(BaiduDramaScanner.class);
        AtomicReference<Runnable> backgroundTask = new AtomicReference<>();
        BaiduScanController controller = controller(scanner, backgroundTask::set);
        com.onehot.aidrama.dramas.Drama drama = new com.onehot.aidrama.dramas.Drama();
        drama.setId("drama-1");
        when(scanner.syncImportedAssets(List.of("drama-1", "drama-2")))
                .thenReturn(new BaiduDramaScanner.SyncResult(2, 2, 0, List.of(drama), List.of()));

        var response = controller.syncAssets(new BaiduScanController.SyncAssetsRequest(List.of("drama-1", "drama-2")));

        assertThat(response.data().requested()).isEqualTo(2);
        assertThat(response.data().acceptedAt()).isNotNull();
        verify(scanner, never()).syncImportedAssets(List.of("drama-1", "drama-2"));

        backgroundTask.get().run();

        verify(scanner).syncImportedAssets(List.of("drama-1", "drama-2"));
    }

    @Test
    void acceptsClientCompleteFormSubmissionForSummaryOnlySync() {
        BaiduDramaScanner scanner = mock(BaiduDramaScanner.class);
        BaiduScanController controller = controller(scanner, Runnable::run);
        com.onehot.aidrama.dramas.Drama drama = new com.onehot.aidrama.dramas.Drama();
        drama.setId("drama-1");
        drama.setSummary("原始简介");
        drama.setCoverUrl("/covers/cover.jpg");
        when(scanner.applyClientAssetSync("drama-1", "原始简介", null, null)).thenReturn(drama);

        var response = controller.clientSyncCompleteForm("drama-1", "原始简介", null);

        assertThat(response.data().dramaId()).isEqualTo("drama-1");
        assertThat(response.data().summary()).isEqualTo("原始简介");
        assertThat(response.data().coverUrl()).isEqualTo("/covers/cover.jpg");
        verify(scanner).applyClientAssetSync("drama-1", "原始简介", null, null);
    }

    @Test
    void statusIncludesLatestBaiduScanTaskProgress() {
        BaiduDramaScanner scanner = mock(BaiduDramaScanner.class);
        SystemTaskRepository repository = systemTaskRepository();
        BaiduScanController controller = new BaiduScanController(
                scanner,
                Runnable::run,
                new SystemTaskService(repository),
                repository
        );
        SystemTask task = new SystemTask();
        task.setType(SystemTaskType.BAIDU_PAN_SCAN);
        task.setStatus(SystemTaskStatus.SUCCEEDED);
        task.setSummary("导入 3 部短剧");
        task.setResultPayload(Map.of("importedCount", "3"));
        task.setStartedAt(Instant.parse("2026-09-14T06:00:00Z"));
        task.setFinishedAt(Instant.parse("2026-09-14T06:00:05Z"));
        when(scanner.lastScanAt()).thenReturn(Optional.of("2026-09-14T06:00:05Z"));
        when(repository.findFirstByTypeOrderByStartedAtDesc(SystemTaskType.BAIDU_PAN_SCAN))
                .thenReturn(Optional.of(task));

        var response = controller.status();

        assertThat(response.data().lastScanAt()).isEqualTo(Instant.parse("2026-09-14T06:00:05Z"));
        assertThat(response.data().taskStatus()).isEqualTo(SystemTaskStatus.SUCCEEDED);
        assertThat(response.data().taskSummary()).isEqualTo("导入 3 部短剧");
        assertThat(response.data().taskStartedAt()).isEqualTo(Instant.parse("2026-09-14T06:00:00Z"));
        assertThat(response.data().taskFinishedAt()).isEqualTo(Instant.parse("2026-09-14T06:00:05Z"));
        assertThat(response.data().importedCount()).isEqualTo(3);
    }

    private BaiduScanController controller(BaiduDramaScanner scanner, TaskExecutor taskExecutor) {
        SystemTaskRepository repository = systemTaskRepository();
        return new BaiduScanController(scanner, taskExecutor, new SystemTaskService(repository), repository);
    }

    private SystemTaskRepository systemTaskRepository() {
        SystemTaskRepository repository = mock(SystemTaskRepository.class);
        when(repository.save(any(SystemTask.class))).thenAnswer(invocation -> invocation.getArgument(0));
        when(repository.findFirstByTypeOrderByStartedAtDesc(SystemTaskType.BAIDU_PAN_SCAN))
                .thenReturn(Optional.empty());
        return repository;
    }

}
