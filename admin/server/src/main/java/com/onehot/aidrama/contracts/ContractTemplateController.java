package com.onehot.aidrama.contracts;

import com.onehot.aidrama.common.ApiResponse;
import com.onehot.aidrama.common.TraceIdFilter;
import com.onehot.aidrama.media.MediaPlatform;
import org.slf4j.MDC;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;

@RestController
public class ContractTemplateController {
    private final ContractTemplateService service;
    private final ContractTemplateStorage storage;

    public ContractTemplateController(ContractTemplateService service, ContractTemplateStorage storage) {
        this.service = service;
        this.storage = storage;
    }

    @GetMapping("/api/admin/contract-templates")
    ApiResponse<List<ContractTemplateDtos.ContractTemplateResponse>> list() {
        return ApiResponse.ok(service.list(), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @GetMapping("/api/desktop/contract-templates")
    ApiResponse<List<ContractTemplateDtos.ContractTemplateResponse>> desktopList(
            @RequestParam(defaultValue = "WECHAT_VIDEO") MediaPlatform platform,
            @RequestParam ContractTemplateType type
    ) {
        return ApiResponse.ok(service.listByPlatformAndType(platform, type), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PostMapping("/api/admin/contract-templates")
    ApiResponse<ContractTemplateDtos.ContractTemplateResponse> create(
            @RequestParam(defaultValue = "WECHAT_VIDEO") MediaPlatform platform,
            @RequestParam ContractTemplateType type,
            @RequestParam(required = false) String name,
            @RequestParam("file") MultipartFile file
    ) {
        return ApiResponse.ok(
                ContractTemplateDtos.ContractTemplateResponse.from(service.create(platform, type, name, file, storage)),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @PostMapping("/api/admin/contract-templates/{id}/file")
    ApiResponse<ContractTemplateDtos.ContractTemplateResponse> replaceFile(
            @PathVariable String id,
            @RequestParam("file") MultipartFile file
    ) {
        return ApiResponse.ok(
                ContractTemplateDtos.ContractTemplateResponse.from(service.replaceFile(id, file, storage)),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @DeleteMapping("/api/admin/contract-templates/{id}")
    ApiResponse<Void> delete(@PathVariable String id) {
        service.delete(id);
        return ApiResponse.ok(null, MDC.get(TraceIdFilter.TRACE_ID));
    }
}
