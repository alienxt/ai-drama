package com.onehot.aidrama.baiduyun;

import com.onehot.aidrama.common.ApiResponse;
import com.onehot.aidrama.common.TraceIdFilter;
import com.onehot.aidrama.dramas.Drama;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.core.task.TaskExecutor;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.List;

@RestController
@RequestMapping("/api/admin/dramas")
public class BaiduScanController {
    private static final Logger LOGGER = LoggerFactory.getLogger(BaiduScanController.class);

    private final BaiduDramaScanner scanner;
    private final BaiduDramaPreparationService preparationService;
    private final TaskExecutor taskExecutor;

    public BaiduScanController(BaiduDramaScanner scanner, BaiduDramaPreparationService preparationService, TaskExecutor taskExecutor) {
        this.scanner = scanner;
        this.preparationService = preparationService;
        this.taskExecutor = taskExecutor;
    }

    @PostMapping("/scan-baidu")
    ApiResponse<ScanAccepted> scan(@RequestBody ScanRequest request) {
        Instant acceptedAt = Instant.now();
        taskExecutor.execute(() -> {
            try {
                List<Drama> dramas = request.remoteRoot() == null || request.remoteRoot().isBlank()
                        ? scanner.scanLatestConfiguredRoot()
                        : scanner.scanLatestDate(request.remoteRoot());
                LOGGER.info("Baidu scan finished: imported={}", dramas.size());
                prepareAll(dramas);
            } catch (RuntimeException exception) {
                LOGGER.error("Baidu scan failed", exception);
            }
        });
        return ApiResponse.ok(new ScanAccepted(acceptedAt), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PostMapping("/repair-baidu-assets")
    ApiResponse<List<Drama>> repairAssets() {
        return ApiResponse.ok(scanner.repairImportedAssets(), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PostMapping("/sync-assets")
    ApiResponse<SyncAssetsAccepted> syncAssets(@RequestBody SyncAssetsRequest request) {
        List<String> ids = normalizeIds(request == null ? null : request.ids());
        taskExecutor.execute(() -> {
            try {
                BaiduDramaScanner.SyncResult result = scanner.syncImportedAssets(ids);
                LOGGER.info(
                        "Baidu asset sync finished: requested={}, succeeded={}, failed={}",
                        result.requested(),
                        result.succeeded(),
                        result.failed()
                );
                prepareAll(result.dramas());
            } catch (RuntimeException exception) {
                LOGGER.error("Baidu asset sync failed", exception);
            }
        });
        return ApiResponse.ok(new SyncAssetsAccepted(ids.size(), Instant.now()), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @GetMapping("/scan-baidu/status")
    ApiResponse<ScanStatus> status() {
        return ApiResponse.ok(new ScanStatus(scanner.lastScanAt().map(Instant::parse).orElse(null)), MDC.get(TraceIdFilter.TRACE_ID));
    }

    public record ScanRequest(String remoteRoot) {
    }

    public record ScanStatus(Instant lastScanAt) {
    }

    public record ScanAccepted(Instant acceptedAt) {
    }

    public record SyncAssetsRequest(List<String> ids) {
    }

    public record SyncAssetsAccepted(int requested, Instant acceptedAt) {
    }

    private List<String> normalizeIds(List<String> ids) {
        if (ids == null) {
            return List.of();
        }
        return ids.stream()
                .filter(id -> id != null && !id.isBlank())
                .distinct()
                .toList();
    }

    private void prepareAll(List<Drama> dramas) {
        if (dramas == null || dramas.isEmpty()) {
            return;
        }
        for (Drama drama : dramas) {
            try {
                Drama prepared = preparationService.prepareForDistribution(drama);
                LOGGER.info(
                        "Baidu drama preparation finished: dramaId={}, status={}, aiTitle={}, aiCoverUrl={}",
                        drama.getId(),
                        prepared == null ? null : prepared.getStatus(),
                        prepared == null ? null : prepared.getAiTitle(),
                        prepared == null ? null : prepared.getAiCoverUrl()
                );
            } catch (RuntimeException exception) {
                LOGGER.error("Baidu drama preparation failed: dramaId={}", drama == null ? null : drama.getId(), exception);
            }
        }
    }
}
