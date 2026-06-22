package com.onehot.aidrama.contracts;

import com.onehot.aidrama.media.MediaPlatform;

import java.time.Instant;

public class ContractTemplateDtos {
    public record ContractTemplateResponse(
            String id,
            MediaPlatform platform,
            String platformLabel,
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
                    template.getPlatform(),
                    labelForPlatform(template.getPlatform()),
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

    private static String labelForPlatform(MediaPlatform platform) {
        return switch (platform == null ? MediaPlatform.WECHAT_VIDEO : platform) {
            case WECHAT_VIDEO -> "视频号";
            case DOUYIN -> "抖音";
            case TIKTOK -> "TK";
        };
    }
}
