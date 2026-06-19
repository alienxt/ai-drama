package com.onehot.aidrama.common.config;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class StaticPageControllerTest {
    private final StaticPageController controller = new StaticPageController();

    @Test
    void forwardsAdminRoutesToFrontendIndex() {
        assertThat(controller.forward()).isEqualTo("forward:/index.html");
    }
}
