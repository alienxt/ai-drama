package com.onehot.aidrama.categories;

import jakarta.validation.constraints.NotBlank;

public record CategoryRequest(@NotBlank String name, @NotBlank String code, boolean enabled, int sortOrder) {
}

