package com.onehot.aidrama.users;

import java.time.Instant;
import java.util.List;

public record AccountDto(
        String id,
        String username,
        List<String> roles,
        boolean enabled,
        String boundDeviceId,
        String lastLoginDeviceId,
        Instant lastLoginAt
) {
    public static AccountDto from(Account account) {
        return new AccountDto(
                account.getId(),
                account.getUsername(),
                account.getRoles(),
                account.isEnabled(),
                account.getBoundDeviceId(),
                account.getLastLoginDeviceId(),
                account.getLastLoginAt()
        );
    }
}
