package com.onehot.aidrama.baiduyun;

import com.onehot.aidrama.common.ApiResponse;
import com.onehot.aidrama.common.TraceIdFilter;
import com.onehot.aidrama.dramas.Drama;
import com.onehot.aidrama.system.SystemTaskService;
import com.onehot.aidrama.system.SystemTaskType;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.core.task.TaskExecutor;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/admin/dramas")
public class BaiduScanController {
    private static final Logger LOGGER = LoggerFactory.getLogger(BaiduScanController.class);

    private final BaiduDramaScanner scanner;
    private final BaiduDramaPreparationService preparationService;
    private final TaskExecutor taskExecutor;
    private final SystemTaskService systemTaskService;

    public BaiduScanController(
            BaiduDramaScanner scanner,
            BaiduDramaPreparationService preparationService,
            TaskExecutor taskExecutor,
            SystemTaskService systemTaskService
    ) {
        this.scanner = scanner;
        this.preparationService = preparationService;
        this.taskExecutor = taskExecutor;
        this.systemTaskService = systemTaskService;
    }

    @PostMapping("/scan-baidu")
    ApiResponse<ScanAccepted> scan(@RequestBody ScanRequest request) {
        Instant acceptedAt = Instant.now();
        String remoteRoot = request == null ? null : request.remoteRoot();
        taskExecutor.execute(() -> {
            try {
                systemTaskService.run(
                        SystemTaskType.BAIDU_PAN_SCAN,
                        "扫描百度网盘",
                        "manual",
                        mapOf("remoteRoot", remoteRoot == null || remoteRoot.isBlank() ? "configured" : remoteRoot),
                        () -> {
                            List<Drama> dramas = remoteRoot == null || remoteRoot.isBlank()
                                    ? scanner.scanLatestConfiguredRoot()
                                    : scanner.scanLatestDate(remoteRoot);
                            LOGGER.info("Baidu scan finished: imported={}", dramas.size());
                            PrepareResult prepareResult = prepareAll(dramas);
                            return new ScanResult(dramas, prepareResult);
                        },
                        this::scanTaskResult
                );
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

    private PrepareResult prepareAll(List<Drama> dramas) {
        if (dramas == null || dramas.isEmpty()) {
            return new PrepareResult(0, 0, List.of());
        }
        int succeeded = 0;
        List<Map<String, Object>> failures = new java.util.ArrayList<>();
        for (Drama drama : dramas) {
            try {
                Drama prepared = preparationService.prepareForDistribution(drama);
                succeeded++;
                LOGGER.info(
                        "Baidu drama preparation finished: dramaId={}, status={}, aiTitle={}, aiCoverUrl={}",
                        drama.getId(),
                        prepared == null ? null : prepared.getStatus(),
                        prepared == null ? null : prepared.getAiTitle(),
                        prepared == null ? null : prepared.getAiCoverUrl()
                );
            } catch (RuntimeException exception) {
                LOGGER.error("Baidu drama preparation failed: dramaId={}", drama == null ? null : drama.getId(), exception);
                failures.add(mapOf(
                        "dramaId", drama == null ? null : drama.getId(),
                        "title", drama == null ? null : drama.getTitle(),
                        "message", exception.getMessage()
                ));
            }
        }
        return new PrepareResult(succeeded, failures.size(), failures);
    }

    private SystemTaskService.TaskResult scanTaskResult(ScanResult result) {
        List<Drama> dramas = result.dramas() == null ? List.of() : result.dramas();
        PrepareResult prepare = result.prepareResult();
        return new SystemTaskService.TaskResult(
                "导入 %d 部短剧，准备成功 %d 部，失败 %d 部".formatted(
                        dramas.size(),
                        prepare.succeeded(),
                        prepare.failed()
                ),
                mapOf(
                        "importedCount", dramas.size(),
                        "preparedCount", prepare.succeeded(),
                        "prepareFailedCount", prepare.failed(),
                        "dramas", dramas.stream().map(this::dramaSummary).toList(),
                        "prepareFailures", prepare.failures()
                )
        );
    }

    private Map<String, Object> dramaSummary(Drama drama) {
        return mapOf(
                "id", drama.getId(),
                "title", drama.getTitle(),
                "sourcePath", drama.getSourcePath(),
                "episodeCount", drama.getEpisodes() == null ? 0 : drama.getEpisodes().size(),
                "status", drama.getStatus()
        );
    }

    private Map<String, Object> mapOf(Object... pairs) {
        Map<String, Object> values = new LinkedHashMap<>();
        for (int index = 0; index < pairs.length; index += 2) {
            values.put(String.valueOf(pairs[index]), pairs[index + 1]);
        }
        return values;
    }

    private record ScanResult(List<Drama> dramas, PrepareResult prepareResult) {
    }

    private record PrepareResult(int succeeded, int failed, List<Map<String, Object>> failures) {
    }
}
