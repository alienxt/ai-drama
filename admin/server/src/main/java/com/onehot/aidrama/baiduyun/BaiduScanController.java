package com.onehot.aidrama.baiduyun;

import com.onehot.aidrama.common.ApiResponse;
import com.onehot.aidrama.common.TraceIdFilter;
import com.onehot.aidrama.dramas.Drama;
import com.onehot.aidrama.system.SystemTaskService;
import com.onehot.aidrama.system.SystemTaskType;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.http.MediaType;
import org.springframework.core.task.TaskExecutor;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/admin/dramas")
public class BaiduScanController {
    private static final Logger LOGGER = LoggerFactory.getLogger(BaiduScanController.class);

    private final BaiduDramaScanner scanner;
    private final TaskExecutor taskExecutor;
    private final SystemTaskService systemTaskService;

    public BaiduScanController(
            BaiduDramaScanner scanner,
            TaskExecutor taskExecutor,
            SystemTaskService systemTaskService
    ) {
        this.scanner = scanner;
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
                            return dramas;
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
            } catch (RuntimeException exception) {
                LOGGER.error("Baidu asset sync failed", exception);
            }
        });
        return ApiResponse.ok(new SyncAssetsAccepted(ids.size(), Instant.now()), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PostMapping("/sync-assets/client-plan")
    ApiResponse<ClientSyncPlanResponse> clientSyncPlan(@RequestBody SyncAssetsRequest request) {
        List<String> ids = normalizeIds(request == null ? null : request.ids());
        List<BaiduDramaScanner.ClientAssetSyncPlan> plans = scanner.clientAssetSyncPlans(ids);
        return ApiResponse.ok(new ClientSyncPlanResponse(plans), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PostMapping(value = "/sync-assets/client-complete/{id}", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    ApiResponse<ClientSyncCompleteResponse> clientSyncComplete(
            @PathVariable String id,
            @RequestParam(required = false) String summary,
            @RequestParam(required = false) String coverPath,
            @RequestPart(required = false) MultipartFile cover
    ) throws IOException {
        byte[] coverBytes = cover == null || cover.isEmpty() ? null : cover.getBytes();
        Drama drama = scanner.applyClientAssetSync(id, summary, coverPath, coverBytes);
        return ApiResponse.ok(new ClientSyncCompleteResponse(drama.getId(), drama.getCoverUrl(), drama.getSummary()), MDC.get(TraceIdFilter.TRACE_ID));
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

    public record ClientSyncPlanResponse(List<BaiduDramaScanner.ClientAssetSyncPlan> items) {
    }

    public record ClientSyncCompleteResponse(String dramaId, String coverUrl, String summary) {
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

    private SystemTaskService.TaskResult scanTaskResult(List<Drama> dramas) {
        dramas = dramas == null ? List.of() : dramas;
        return new SystemTaskService.TaskResult(
                "导入 %d 部短剧".formatted(dramas.size()),
                mapOf(
                        "importedCount", dramas.size(),
                        "dramas", dramas.stream().map(this::dramaSummary).toList()
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

}
