package com.onehot.aidrama.users;

import java.time.Instant;
import java.util.List;

public record AccountDto(
        String id,
        String username,
        List<String> roles,
        boolean enabled,
        int dailyClaimLimit,
        long todayClaimCount,
        String boundDeviceId,
        String lastLoginDeviceId,
        Instant lastLoginAt
) {
    public static AccountDto from(Account account) {
        return from(account, 0);
    }

    public static AccountDto from(Account account, long todayClaimCount) {
        return new AccountDto(
                account.getId(),
                account.getUsername(),
                account.getRoles(),
                account.isEnabled(),
                account.getDailyClaimLimit(),
                todayClaimCount,
                account.getBoundDeviceId(),
                account.getLastLoginDeviceId(),
                account.getLastLoginAt()
        );
    }
}
