package com.onehot.aidrama.configs;

import com.onehot.aidrama.common.ApiResponse;
import com.onehot.aidrama.common.TraceIdFilter;
import org.slf4j.MDC;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DesktopDistributionConfigController {
    private static final double DEFAULT_FREE_EPISODE_RATIO = 0.2d;

    private final SystemConfigService configService;

    public DesktopDistributionConfigController(SystemConfigService configService) {
        this.configService = configService;
    }

    @GetMapping("/api/desktop/distribution-config")
    ApiResponse<DesktopDistributionConfigResponse> desktopConfig() {
        DesktopDistributionConfigResponse response = new DesktopDistributionConfigResponse(
                configDouble("distribution.freeEpisodeRatio", DEFAULT_FREE_EPISODE_RATIO)
        );
        return ApiResponse.ok(response, MDC.get(TraceIdFilter.TRACE_ID));
    }

    private double configDouble(String key, double defaultValue) {
        return configService.get(key)
                .map(value -> {
                    try {
                        double parsed = Double.parseDouble(value);
                        if (Double.isNaN(parsed) || Double.isInfinite(parsed)) {
                            return defaultValue;
                        }
                        return Math.max(0d, Math.min(1d, parsed));
                    } catch (NumberFormatException exception) {
                        return defaultValue;
                    }
                })
                .orElse(defaultValue);
    }

    public record DesktopDistributionConfigResponse(double freeEpisodeRatio) {
    }
}
