package com.onehot.aidrama.users;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import java.util.List;

public record CreateAccountRequest(
        @NotBlank String username,
        @Size(min = 8, message = "密码至少 8 位") String password,
        List<String> roles
) {
}

