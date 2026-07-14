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
public class HongguoAiMangaAutoImportScheduler {
    private static final Logger LOGGER = LoggerFactory.getLogger(HongguoAiMangaAutoImportScheduler.class);
    private static final ZoneId CHINA_ZONE = ZoneId.of("Asia/Shanghai");
    private static final String ENABLED_KEY = "hongguo.aiMangaAutoImportEnabled";
    private static final String DAILY_LIMIT_KEY = "hongguo.aiMangaAutoImportDailyLimit";
    private static final String MAX_PAGES_KEY = "hongguo.aiMangaAutoImportMaxPages";
    private static final String LAST_RUN_DATE_KEY = "hongguo.aiMangaAutoImportLastRunDate";
    private static final String LAST_RUN_AT_KEY = "hongguo.aiMangaAutoImportLastRunAt";

    private final HongguoDramaService dramaService;
    private final SystemConfigService configService;
    private final SystemTaskService systemTaskService;
    private final AtomicBoolean running = new AtomicBoolean(false);

    public HongguoAiMangaAutoImportScheduler(
            HongguoDramaService dramaService,
            SystemConfigService configService,
            SystemTaskService systemTaskService
    ) {
        this.dramaService = dramaService;
        this.configService = configService;
        this.systemTaskService = systemTaskService;
    }

    @Scheduled(cron = "${aidrama.hongguo.ai-manga-auto-import-cron:0 10 3 * * *}", zone = "Asia/Shanghai")
    public void scheduledAutoImport() {
        if (!running.compareAndSet(false, true)) {
            LOGGER.warn("Skip Hongguo AI manga auto import because previous run is still running");
            return;
        }
        try {
            runScheduledAutoImport();
        } finally {
            running.set(false);
        }
    }

    private void runScheduledAutoImport() {
        boolean enabled = configService.get(ENABLED_KEY).map(Boolean::parseBoolean).orElse(true);
        if (!enabled) {
            return;
        }
        LocalDate today = LocalDate.now(CHINA_ZONE);
        String todayText = today.toString();
        if (configService.get(LAST_RUN_DATE_KEY).filter(todayText::equals).isPresent()) {
            LOGGER.info("Skip Hongguo AI manga auto import because {} has already run", todayText);
            return;
        }

        int limit = configInt(DAILY_LIMIT_KEY, 30);
        int maxPages = configInt(MAX_PAGES_KEY, 8);
        HongguoDramaService.AutoImportResult result = systemTaskService.run(
                SystemTaskType.HONGGUO_AI_MANGA_AUTO_IMPORT,
                "红果AI漫剧近3日上新自动导入",
                "scheduled",
                mapOf("date", todayText, "limit", limit, "maxPages", maxPages),
                () -> dramaService.autoImportAiMangaNewDramas(limit, maxPages),
                this::taskResult
        );
        configService.put(LAST_RUN_DATE_KEY, todayText, false);
        configService.put(LAST_RUN_AT_KEY, Instant.now().toString(), false);
        LOGGER.info("Hongguo AI manga auto import finished: imported={}, skippedExisting={}, failed={}",
                result.imported(),
                result.skippedExisting(),
                result.failed());
    }

    private SystemTaskService.TaskResult taskResult(HongguoDramaService.AutoImportResult result) {
        return new SystemTaskService.TaskResult(
                "导入 %d 部，跳过已存在 %d 部，失败 %d 部".formatted(
                        result.imported(),
                        result.skippedExisting(),
                        result.failed()
                ),
                mapOf(
                        "requested", result.requested(),
                        "maxPages", result.maxPages(),
                        "pagesFetched", result.pagesFetched(),
                        "candidatesFetched", result.candidatesFetched(),
                        "created", result.created(),
                        "updated", result.updated(),
                        "skipped", result.skipped(),
                        "queued", result.queued(),
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
