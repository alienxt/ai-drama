import type { Account, AiTask, DistributionTask, Drama, MediaAccount } from './types';

export type MediaPlatform = MediaAccount['platform'];
export type DramaStatus = Drama['status'];
export type MediaAccountStatus = MediaAccount['status'];
export type DistributionTaskStatus = DistributionTask['status'];
export type AiTaskStatus = AiTask['status'];
export type AiTaskType = AiTask['type'];
export type AccountRole = Account['roles'][number];

export const mediaPlatformLabels: Record<MediaPlatform, string> = {
  WECHAT_VIDEO: '视频号',
  TIKTOK: 'TikTok',
  DOUYIN: '抖音',
};

export const mediaPlatformOptions = Object.entries(mediaPlatformLabels).map(([value, label]) => ({
  value,
  label,
}));

export function mediaPlatformLabel(platform: string) {
  return mediaPlatformLabels[platform as MediaPlatform] ?? platform;
}

export const dramaStatusLabels: Record<DramaStatus, string> = {
  DRAFT: '草稿',
  READY: '可分发',
  DISABLED: '停用',
};

export const dramaStatusColors: Record<DramaStatus, string> = {
  DRAFT: 'default',
  READY: 'green',
  DISABLED: 'red',
};

export const dramaStatusOptions = Object.entries(dramaStatusLabels).map(([value, label]) => ({
  value,
  label,
}));

export function dramaStatusLabel(status: string) {
  return dramaStatusLabels[status as DramaStatus] ?? status;
}

export const mediaAccountStatusLabels: Record<MediaAccountStatus, string> = {
  BINDING: '绑定中',
  ACTIVE: '可用',
  PAUSED: '暂停分发',
  EXPIRED: '已过期',
  DISABLED: '停用',
};

export const mediaAccountStatusColors: Record<MediaAccountStatus, string> = {
  BINDING: 'processing',
  ACTIVE: 'green',
  PAUSED: 'default',
  EXPIRED: 'orange',
  DISABLED: 'red',
};

export const mediaAccountStatusOptions = Object.entries(mediaAccountStatusLabels).map(([value, label]) => ({
  value,
  label,
}));

export function mediaAccountStatusLabel(status: string) {
  return mediaAccountStatusLabels[status as MediaAccountStatus] ?? status;
}

export const distributionTaskStatusLabels: Record<DistributionTaskStatus, string> = {
  PENDING: '待处理',
  CLAIMED: '已领取',
  DOWNLOADING: '下载中',
  PROCESSING: '处理中',
  UPLOADING: '上传中',
  SUCCEEDED: '成功',
  FAILED: '失败',
  CANCELLED: '已取消',
};

export const distributionTaskStatusColors: Record<DistributionTaskStatus, string> = {
  PENDING: 'default',
  CLAIMED: 'blue',
  DOWNLOADING: 'processing',
  PROCESSING: 'processing',
  UPLOADING: 'processing',
  SUCCEEDED: 'green',
  FAILED: 'red',
  CANCELLED: 'default',
};

export const distributionTaskStatusOptions = Object.entries(distributionTaskStatusLabels).map(([value, label]) => ({
  value,
  label,
}));

export function distributionTaskStatusLabel(status: string) {
  return distributionTaskStatusLabels[status as DistributionTaskStatus] ?? status;
}

export const aiTaskTypeLabels: Record<AiTaskType, string> = {
  DRAMA_TITLE: 'AI剧名',
  DRAMA_COVER: 'AI封面',
};

export const aiTaskTypeOptions = Object.entries(aiTaskTypeLabels).map(([value, label]) => ({
  value,
  label,
}));

export function aiTaskTypeLabel(type: string) {
  return aiTaskTypeLabels[type as AiTaskType] ?? type;
}

export const aiTaskStatusLabels: Record<AiTaskStatus, string> = {
  RUNNING: '执行中',
  SUCCEEDED: '成功',
  FAILED: '失败',
};

export const aiTaskStatusColors: Record<AiTaskStatus, string> = {
  RUNNING: 'processing',
  SUCCEEDED: 'green',
  FAILED: 'red',
};

export const aiTaskStatusOptions = Object.entries(aiTaskStatusLabels).map(([value, label]) => ({
  value,
  label,
}));

export function aiTaskStatusLabel(status: string) {
  return aiTaskStatusLabels[status as AiTaskStatus] ?? status;
}

export const accountRoleLabels: Record<AccountRole, string> = {
  ADMIN: '超级管理员',
  OPERATOR: '运营人员',
  DESKTOP_USER: '桌面端用户',
};

export function accountRoleLabel(role: string) {
  return accountRoleLabels[role as AccountRole] ?? role;
}
