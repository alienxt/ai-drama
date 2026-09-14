package com.onehot.aidrama.configs;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ConfigDtosTest {
    @Test
    void masksSensitiveConfigByKeyEvenWhenSecretFlagIsMissing() {
        SystemConfig config = new SystemConfig();
        config.setKey("baidu.proxyPassword");
        config.setValue("proxy-password");
        config.setSecret(false);

        ConfigDtos.ConfigResponse response = ConfigDtos.ConfigResponse.from(config);

        assertThat(response.value()).isEqualTo("******");
        assertThat(response.secret()).isTrue();
    }

    @Test
    void keepsNonSensitiveConfigReadable() {
        SystemConfig config = new SystemConfig();
        config.setKey("baidu.scanRoot");
        config.setValue("/drama/真人剧/2026");
        config.setSecret(false);

        ConfigDtos.ConfigResponse response = ConfigDtos.ConfigResponse.from(config);

        assertThat(response.value()).isEqualTo("/drama/真人剧/2026");
        assertThat(response.secret()).isFalse();
    }
}
