package com.onehot.aidrama.auth;

import com.onehot.aidrama.common.ApiResponse;
import com.onehot.aidrama.common.TraceIdFilter;
import com.onehot.aidrama.common.error.BusinessException;
import com.onehot.aidrama.common.security.JwtService;
import com.onehot.aidrama.users.Account;
import com.onehot.aidrama.users.AccountDto;
import com.onehot.aidrama.users.AccountService;
import jakarta.validation.Valid;
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/auth")
public class AuthController {
    private final AccountService accountService;
    private final PasswordEncoder passwordEncoder;
    private final JwtService jwtService;

    public AuthController(AccountService accountService, PasswordEncoder passwordEncoder, JwtService jwtService) {
        this.accountService = accountService;
        this.passwordEncoder = passwordEncoder;
        this.jwtService = jwtService;
    }

    @PostMapping("/login")
    ApiResponse<LoginResponse> login(@Valid @RequestBody LoginRequest request) {
        Account account = accountService.findEnabledByUsername(request.username());
        if (!passwordEncoder.matches(request.password(), account.getPasswordHash())) {
            throw new BusinessException("BAD_CREDENTIALS", "用户名或密码错误", HttpStatus.UNAUTHORIZED);
        }
        accountService.verifyLoginDevice(account, request.deviceId());
        accountService.markLogin(account);
        String token = jwtService.issue(account.getId(), account.getUsername(), account.getRoles());
        return ApiResponse.ok(new LoginResponse(token, AccountDto.from(account)), MDC.get(TraceIdFilter.TRACE_ID));
    }
}
