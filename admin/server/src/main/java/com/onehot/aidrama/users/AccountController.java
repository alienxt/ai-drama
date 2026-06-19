package com.onehot.aidrama.users;

import com.onehot.aidrama.common.ApiResponse;
import com.onehot.aidrama.common.PageResult;
import com.onehot.aidrama.common.TraceIdFilter;
import jakarta.validation.Valid;
import org.slf4j.MDC;
import org.springframework.data.domain.Pageable;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/admin/accounts")
@PreAuthorize("hasRole('ADMIN')")
public class AccountController {
    private final AccountService service;

    public AccountController(AccountService service) {
        this.service = service;
    }

    @GetMapping
    ApiResponse<PageResult<AccountDto>> list(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Boolean enabled,
            @RequestParam(required = false) java.util.List<String> roles,
            Pageable pageable
    ) {
        return ApiResponse.ok(PageResult.from(service.search(keyword, enabled, roles, pageable)), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PostMapping
    ApiResponse<AccountDto> create(@Valid @RequestBody CreateAccountRequest request) {
        return ApiResponse.ok(service.create(request), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PatchMapping("/{id}/enabled")
    ApiResponse<AccountDto> setEnabled(@PathVariable String id, @RequestBody EnabledRequest request) {
        return ApiResponse.ok(service.setEnabled(id, request.enabled()), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PatchMapping("/{id}/device-binding")
    ApiResponse<AccountDto> bindDevice(@PathVariable String id, @RequestBody DeviceBindingRequest request) {
        return ApiResponse.ok(service.bindDevice(id, request.deviceId()), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @DeleteMapping("/{id}/device-binding")
    ApiResponse<AccountDto> clearDeviceBinding(@PathVariable String id) {
        return ApiResponse.ok(service.clearDeviceBinding(id), MDC.get(TraceIdFilter.TRACE_ID));
    }

    public record EnabledRequest(boolean enabled) {
    }

    public record DeviceBindingRequest(String deviceId) {
    }
}
