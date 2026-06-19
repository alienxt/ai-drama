package com.onehot.aidrama.auth;

import com.onehot.aidrama.users.AccountDto;

public record LoginResponse(String token, AccountDto account) {
}

