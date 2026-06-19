package com.onehot.aidrama.common.security;

import java.util.List;

public record JwtPrincipal(String accountId, String username, List<String> roles) {
}

