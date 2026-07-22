package com.onehot.aidrama.configs;

import com.onehot.aidrama.common.ApiResponse;
import com.onehot.aidrama.common.TraceIdFilter;
import org.slf4j.MDC;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StoryboardConfigController {
    private static final String DEFAULT_API_BASE = "https://api.deepseek.com";
    private static final String DEFAULT_MODEL = "deepseek-v4-pro";
    private static final String DEFAULT_STYLE = "真人风格-国产都市";
    private static final int DEFAULT_TARGET_SHOTS = 15;

    private final SystemConfigService configService;

    public StoryboardConfigController(SystemConfigService configService) {
        this.configService = configService;
    }

    @GetMapping("/api/desktop/storyboard-config")
    ApiResponse<StoryboardConfigResponse> desktopConfig() {
        StoryboardConfigResponse response = new StoryboardConfigResponse(
                configBoolean("storyboard.enabled", false),
                config("storyboard.deepseekApiBase", DEFAULT_API_BASE),
                secretConfig("storyboard.deepseekApiKey", "DEEPSEEK_API_KEY"),
                config("storyboard.deepseekModel", DEFAULT_MODEL),
                configInt("storyboard.targetShots", DEFAULT_TARGET_SHOTS),
                config("storyboard.style", DEFAULT_STYLE)
        );
        return ApiResponse.ok(response, MDC.get(TraceIdFilter.TRACE_ID));
    }

    private String config(String key, String defaultValue) {
        return configService.get(key).filter(value -> !value.isBlank()).orElse(defaultValue);
    }

    private String secretConfig(String primaryKey, String fallbackKey) {
        return configService.get(primaryKey)
                .filter(value -> !value.isBlank())
                .or(() -> configService.get(fallbackKey).filter(value -> !value.isBlank()))
                .orElse("");
    }

    private boolean configBoolean(String key, boolean defaultValue) {
        return configService.get(key)
                .map(Boolean::parseBoolean)
                .orElse(defaultValue);
    }

    private int configInt(String key, int defaultValue) {
        return configService.get(key)
                .map(value -> {
                    try {
                        return Math.max(Integer.parseInt(value), 1);
                    } catch (NumberFormatException exception) {
                        return defaultValue;
                    }
                })
                .orElse(defaultValue);
    }

    public record StoryboardConfigResponse(
            boolean enabled,
            String deepseekApiBase,
            String deepseekApiKey,
            String deepseekModel,
            int targetShots,
            String style
    ) {
    }
}
