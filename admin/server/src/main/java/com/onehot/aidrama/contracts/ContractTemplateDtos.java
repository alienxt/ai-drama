package com.onehot.aidrama.contracts;

import java.time.Instant;

public class ContractTemplateDtos {
    public record ContractTemplateResponse(
            String id,
            ContractTemplateType type,
            String label,
            String name,
            String fileName,
            long fileSize,
            String downloadUrl,
            Instant uploadedAt,
            Instant createdAt,
            Instant updatedAt
    ) {
        public static ContractTemplateResponse from(ContractTemplate template) {
            return new ContractTemplateResponse(
                    template.getId(),
                    template.getType(),
                    template.getType().getLabel(),
                    template.getName(),
                    template.getFileName(),
                    template.getFileSize(),
                    template.getDownloadUrl(),
                    template.getUploadedAt(),
                    template.getCreatedAt(),
                    template.getUpdatedAt()
            );
        }
    }
}
