package com.onehot.aidrama;

import com.onehot.aidrama.common.security.JwtPrincipal;
import com.onehot.aidrama.common.security.JwtService;
import com.onehot.aidrama.common.security.SecurityProperties;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class JwtServiceTest {
    @Test
    void issueAndParseToken() {
        JwtService service = new JwtService(new SecurityProperties("a-secret-that-is-long-enough", 60));

        String token = service.issue("account-1", "admin", List.of("ADMIN"));
        JwtPrincipal principal = service.parse(token);

        assertThat(principal.accountId()).isEqualTo("account-1");
        assertThat(principal.username()).isEqualTo("admin");
        assertThat(principal.roles()).containsExactly("ADMIN");
    }
}

