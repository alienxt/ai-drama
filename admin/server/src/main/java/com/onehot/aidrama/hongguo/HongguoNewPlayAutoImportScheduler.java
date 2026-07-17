package com.onehot.aidrama.hongguo;

import com.onehot.aidrama.configs.SystemConfigService;
import com.onehot.aidrama.system.SystemTaskService;
import com.onehot.aidrama.system.SystemTaskType;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

@Service
public class HongguoNewPlayAutoImportScheduler {
    private static final Logger LOGGER = LoggerFactory.getLogger(HongguoNewPlayAutoImportScheduler.class);
    private static final ZoneId CHINA_ZONE = ZoneId.of("Asia/Shanghai");
    private static final String ENABLED_KEY = "hongguo.newPlayAutoImportEnabled";
    private static final String MAX_PAGES_KEY = "hongguo.newPlayAutoImportMaxPages";
    private static final String LAST_RUN_AT_KEY = "hongguo.newPlayAutoImportLastRunAt";

    private final HongguoDramaService dramaService;
    private final SystemConfigService configService;
    private final SystemTaskService systemTaskService;
    private final AtomicBoolean running = new AtomicBoolean(false);

    public HongguoNewPlayAutoImportScheduler(
            HongguoDramaService dramaService,
            SystemConfigService configService,
            SystemTaskService systemTaskService
    ) {
        this.dramaService = dramaService;
        this.configService = configService;
        this.systemTaskService = systemTaskService;
    }

    @Scheduled(cron = "${aidrama.hongguo.new-play-auto-import-cron:0 0 2-22 * * *}", zone = "Asia/Shanghai")
    public void scheduledHourlyAutoImport() {
        runOnce("hourly");
    }

    @Scheduled(cron = "${aidrama.hongguo.new-play-auto-import-peak-cron:0 */10 23,0 * * *}", zone = "Asia/Shanghai")
    public void scheduledPeakAutoImport() {
        runOnce("peak");
    }

    private void runOnce(String triggerSource) {
        if (!running.compareAndSet(false, true)) {
            LOGGER.warn("Skip Hongguo new play auto import because previous run is still running");
            return;
        }
        try {
            runScheduledAutoImport(triggerSource);
        } finally {
            running.set(false);
        }
    }

    private void runScheduledAutoImport(String triggerSource) {
        boolean enabled = configService.get(ENABLED_KEY).map(Boolean::parseBoolean).orElse(true);
        if (!enabled) {
            return;
        }
        LocalDate today = LocalDate.now(CHINA_ZONE);
        int maxPages = Math.min(
                configInt(MAX_PAGES_KEY, HongguoDramaService.DEFAULT_NEW_PLAY_AUTO_IMPORT_MAX_PAGES),
                HongguoDramaService.DEFAULT_NEW_PLAY_AUTO_IMPORT_MAX_PAGES
        );
        HongguoDramaService.NewPlayAutoImportResult result = systemTaskService.run(
                SystemTaskType.HONGGUO_NEW_PLAY_AUTO_IMPORT,
                "红果新剧小时自动导入",
                "scheduled-" + triggerSource,
                mapOf("date", today.toString(), "maxPages", maxPages),
                () -> dramaService.autoImportTodayNewPlayDramas(maxPages),
                this::taskResult
        );
        configService.put(LAST_RUN_AT_KEY, Instant.now().toString(), false);
        LOGGER.info("Hongguo new play auto import finished: date={}, pagesFetched={}, imported={}, skippedExisting={}, failed={}",
                result.date(),
                result.pagesFetched(),
                result.imported(),
                result.skippedExisting(),
                result.failed());
    }

    private SystemTaskService.TaskResult taskResult(HongguoDramaService.NewPlayAutoImportResult result) {
        return new SystemTaskService.TaskResult(
                "导入 %d 部，跳过已存在 %d 部，失败 %d 部".formatted(
                        result.imported(),
                        result.skippedExisting(),
                        result.failed()
                ),
                mapOf(
                        "date", result.date(),
                        "maxPages", result.maxPages(),
                        "pagesFetched", result.pagesFetched(),
                        "candidatesFetched", result.candidatesFetched(),
                        "created", result.created(),
                        "updated", result.updated(),
                        "skipped", result.skipped(),
                        "imported", result.imported(),
                        "skippedExisting", result.skippedExisting(),
                        "failed", result.failed(),
                        "importedDramas", result.importedDramas(),
                        "failures", result.failures()
                )
        );
    }

    private int configInt(String key, int defaultValue) {
        return configService.get(key)
                .filter(value -> !value.isBlank())
                .map(value -> {
                    try {
                        return Math.max(1, Integer.parseInt(value.trim()));
                    } catch (NumberFormatException exception) {
                        return defaultValue;
                    }
                })
                .orElse(defaultValue);
    }

    private Map<String, Object> mapOf(Object... pairs) {
        Map<String, Object> values = new LinkedHashMap<>();
        for (int index = 0; index < pairs.length; index += 2) {
            values.put(String.valueOf(pairs[index]), pairs[index + 1]);
        }
        return values;
    }
}
