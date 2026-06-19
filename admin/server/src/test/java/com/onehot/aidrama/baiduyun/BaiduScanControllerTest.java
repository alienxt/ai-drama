package com.onehot.aidrama.baiduyun;

import com.onehot.aidrama.system.SystemTask;
import com.onehot.aidrama.system.SystemTaskRepository;
import com.onehot.aidrama.system.SystemTaskService;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.mockito.ArgumentMatchers.any;

class BaiduScanControllerTest {
    @Test
    void acceptsBaiduScanWithoutRunningScannerOnRequestThread() {
        BaiduDramaScanner scanner = mock(BaiduDramaScanner.class);
        List<Runnable> backgroundTasks = new ArrayList<>();
        BaiduScanController controller = new BaiduScanController(scanner, backgroundTasks::add, systemTaskService());
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
        BaiduScanController controller = new BaiduScanController(scanner, backgroundTask::set, systemTaskService());
        com.onehot.aidrama.dramas.Drama drama = new com.onehot.aidrama.dramas.Drama();
        drama.setId("drama-1");
        when(scanner.syncImportedAssets(List.of("drama-1", "drama-2")))
                .thenReturn(new BaiduDramaScanner.SyncResult(2, 2, 0, List.of(drama)));

        var response = controller.syncAssets(new BaiduScanController.SyncAssetsRequest(List.of("drama-1", "drama-2")));

        assertThat(response.data().requested()).isEqualTo(2);
        assertThat(response.data().acceptedAt()).isNotNull();
        verify(scanner, never()).syncImportedAssets(List.of("drama-1", "drama-2"));

        backgroundTask.get().run();

        verify(scanner).syncImportedAssets(List.of("drama-1", "drama-2"));
    }

    private SystemTaskService systemTaskService() {
        SystemTaskRepository repository = mock(SystemTaskRepository.class);
        when(repository.save(any(SystemTask.class))).thenAnswer(invocation -> invocation.getArgument(0));
        return new SystemTaskService(repository);
    }
}
