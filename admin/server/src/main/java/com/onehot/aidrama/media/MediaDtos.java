package com.onehot.aidrama.media;

public class MediaDtos {
    public record CreateMediaAccountRequest(MediaPlatform platform, String displayName, String externalAccountId, String deviceId) {
    }

    public record LoginStateRequest(String loginStateRef, String deviceId, boolean verified) {
    }

    public record StatusRequest(MediaAccountStatus status) {
    }
}
