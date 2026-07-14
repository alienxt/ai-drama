export type PageResult<T> = {
  content: T[];
  totalElements: number;
  totalPages: number;
  page: number;
  size: number;
};

export type Account = {
  id: string;
  username: string;
  roles: string[];
  enabled: boolean;
  boundDeviceId?: string;
  lastLoginDeviceId?: string;
  lastLoginAt?: string;
};

export type DramaCategory = {
  id: string;
  name: string;
  code: string;
  enabled: boolean;
  sortOrder: number;
};

export type Drama = {
  id: string;
  title: string;
  aiTitle?: string;
  aiTitleEn?: string;
  summary?: string;
  aiSummary?: string;
  aiSummaryEn?: string;
  coverUrl?: string;
  aiCoverUrl?: string;
  aiVideoCoverUrl?: string;
  aiCoverEnUrl?: string;
  aiVideoCoverEnUrl?: string;
  aiCoverGenerating?: boolean;
  rating?: number;
  totalMinutes?: number;
  costAmountWan?: number;
  categoryIds: string[];
  source?: 'BAIDU_PAN' | 'HONGGUO_52API';
  sourcePath?: string;
  providerName?: string;
  providerDramaId?: string;
  publishedAt?: string;
  status: 'DRAFT' | 'READY' | 'DISABLED';
  episodes: { episodeNo: number; title?: string; sourcePath: string; providerVideoId?: string; size: number }[];
  createdAt?: string;
  updatedAt?: string;
};

export type AdminEpisode = {
  episodeNo: number;
  title?: string;
  sourcePath: string;
  size: number;
  downloaded: boolean;
  playSource: 'LOCAL' | 'BAIDU' | 'HONGGUO';
  localUrl?: string;
};

export type EpisodePlaySource = {
  episodeNo: number;
  source: 'LOCAL' | 'BAIDU' | 'HONGGUO';
  downloaded: boolean;
  playUrl: string;
};

export type HongguoCandidate = {
  id: string;
  providerDramaId: string;
  title: string;
  summary?: string;
  coverUrl?: string;
  duration?: string;
  score?: string;
  category?: string;
  copyright?: string;
  episodeCount?: number;
  playCount?: number;
  categories?: string[];
  calendarDate?: string;
  calendarPage?: number;
  searchKeyword?: string;
  searchPage?: number;
  publishedAt?: string;
  status: 'NEW' | 'IMPORTED' | 'SKIPPED';
  importedDramaId?: string;
  createdAt?: string;
  updatedAt?: string;
};

export type HongguoMangaSyncResponse = {
  keyword: string;
  page: number;
  fetched: number;
  detailed: number;
  skipped: number;
  created: number;
  updated: number;
};

export type HongguoImportCandidateResponse = {
  drama: Drama;
};

export type HongguoCoverBackfillResponse = {
  requested: number;
  updated: number;
  skipped: number;
  failed: number;
};

export type BaiduScanStatus = {
  lastScanAt?: string;
};

export type BaiduScanAccepted = {
  acceptedAt?: string;
};

export type DramaAssetSyncAccepted = {
  requested: number;
  acceptedAt?: string;
};

export type DramaBatchFreshResponse = {
  requested: number;
  updated: number;
  updatedAt?: string;
};

export type DramaBackfillTotalMinutesResponse = {
  requested: number;
  updated: number;
  updatedAt?: string;
};

export type DramaBackfillAiSummariesAccepted = {
  requested: number;
  acceptedAt?: string;
};

export type DramaClientAssetSyncPlanItem = {
  dramaId: string;
  title?: string;
  sourcePath?: string;
  summaryPath?: string;
  summaryDownloadUrl?: string;
  coverPath?: string;
  coverDownloadUrl?: string;
  errorMessage?: string;
};

export type DramaClientAssetSyncPlan = {
  items: DramaClientAssetSyncPlanItem[];
};

export type DramaClientAssetSyncComplete = {
  dramaId: string;
  coverUrl?: string;
  summary?: string;
};

export type AiCoverGenerationAccepted = {
  dramaId: string;
  acceptedAt?: string;
  recommendedCheckAt?: string;
};

export type MediaAccount = {
  id: string;
  platform: 'WECHAT_VIDEO' | 'DOUYIN' | 'TIKTOK';
  displayName: string;
  externalAccountId?: string;
  status: 'BINDING' | 'ACTIVE' | 'PAUSED' | 'EXPIRED' | 'DISABLED';
  loginStateRef?: string;
  deviceId?: string;
  lastVerifiedAt?: string;
  createdAt?: string;
  distributionPolicy: {
    categoryIds: string[];
    dailyLimit: number;
    intervalMinutes: number;
    enabled: boolean;
    transcodePreset: string;
  };
};

export type DistributionTask = {
  id: string;
  ownerAccountId?: string;
  ownerUsername?: string;
  mediaAccountId: string;
  mediaAccountName?: string;
  platform?: 'WECHAT_VIDEO' | 'DOUYIN' | 'TIKTOK';
  dramaId: string;
  dramaTitle?: string;
  status: 'PENDING' | 'CLAIMED' | 'DOWNLOADING' | 'PROCESSING' | 'UPLOADING' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED';
  progress: number;
  failureReason?: string;
  platformPublishId?: string;
  createdAt?: string;
  finishedAt?: string;
};

export type DistributionTaskStatusCount = {
  status: DistributionTask['status'];
  count: number;
};

export type AiTask = {
  id: string;
  type: 'DRAMA_METADATA' | 'DRAMA_TITLE' | 'DRAMA_SUMMARY' | 'DRAMA_COVER' | 'DRAMA_VIDEO_COVER';
  status: 'RUNNING' | 'SUCCEEDED' | 'FAILED';
  provider?: string;
  model?: string;
  endpoint?: string;
  subjectType?: string;
  subjectId?: string;
  subjectTitle?: string;
  prompt?: string;
  requestPayload?: Record<string, unknown>;
  responsePayload?: Record<string, unknown>;
  errorMessage?: string;
  durationMs?: number;
  startedAt?: string;
  finishedAt?: string;
  createdAt?: string;
  updatedAt?: string;
};

export type SystemTask = {
  id: string;
  type: 'BAIDU_PAN_SCAN' | 'HONGGUO_AI_MANGA_AUTO_IMPORT';
  status: 'RUNNING' | 'SUCCEEDED' | 'FAILED';
  title?: string;
  triggerSource?: string;
  summary?: string;
  requestPayload?: Record<string, unknown>;
  resultPayload?: Record<string, unknown>;
  errorMessage?: string;
  durationMs?: number;
  startedAt?: string;
  finishedAt?: string;
  createdAt?: string;
  updatedAt?: string;
};

export type SystemConfig = {
  key: string;
  value: string;
  secret: boolean;
};

export type DesktopVersion = {
  id: string;
  platform: 'MAC' | 'WINDOWS';
  version: string;
  releaseNotes?: string;
  mandatory: boolean;
  published: boolean;
  fileName?: string;
  fileSize: number;
  downloadUrl?: string;
  createdAt?: string;
  updatedAt?: string;
};

export type ContractTemplate = {
  id: string;
  platform: 'WECHAT_VIDEO' | 'DOUYIN' | 'TIKTOK';
  platformLabel: string;
  type: 'COST_CONTRACT' | 'PURCHASE_CONTRACT' | 'RIGHTS_STATEMENT';
  label: string;
  name: string;
  weight: number;
  fileName?: string;
  fileSize: number;
  downloadUrl?: string;
  uploadedAt?: string;
  createdAt?: string;
  updatedAt?: string;
};

export type DownloadInvite = {
  id: string;
  code: string;
  note?: string;
  enabled: boolean;
  maxUses: number;
  usedCount: number;
  expiresAt?: string;
  lastUsedAt?: string;
  createdAt?: string;
  updatedAt?: string;
};

export type RequestLog = {
  id: string;
  traceId?: string;
  method: string;
  path: string;
  query?: string;
  status: number;
  durationMs: number;
  accountId?: string;
  username?: string;
  clientIp?: string;
  userAgent?: string;
  createdAt?: string;
};

export type ExceptionLog = {
  id: string;
  traceId?: string;
  source?: string;
  method?: string;
  path?: string;
  status: number;
  code: string;
  message: string;
  exceptionClass: string;
  stackTrace?: string;
  accountId?: string;
  username?: string;
  clientIp?: string;
  userAgent?: string;
  createdAt?: string;
};

export type HongguoApiDebugLog = {
  id: string;
  traceId?: string;
  method: 'GET' | 'POST';
  endpoint: string;
  requestUrl?: string;
  requestBody?: string;
  status: number;
  responseBody?: string;
  errorMessage?: string;
  durationMs: number;
  createdAt?: string;
};
