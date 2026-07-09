import { CalendarOutlined, ClockCircleOutlined, CloudSyncOutlined, DeleteOutlined, EditOutlined, FileTextOutlined, InfoCircleOutlined, PictureOutlined, PlusOutlined, RocketOutlined, SearchOutlined, SyncOutlined } from '@ant-design/icons';
import { Alert, Button, Drawer, Form, Image, Input, InputNumber, Modal, Popconfirm, Progress, Select, Space, Spin, Tag, Tooltip, Typography } from 'antd';
import type { Key, ReactNode } from 'react';
import { useMemo, useState } from 'react';
import { AdminTable } from '../../components/AdminTable';
import { DataPage } from '../../components/DataPage';
import { TableToolbar } from '../../components/TableToolbar';
import { appMessage } from '../../shared/appMessage';
import { formatDateTime } from '../../shared/format';
import { apiDelete, apiGet, apiGetPage, apiPost, apiPut, http } from '../../shared/http';
import { dramaStatusColors, dramaStatusLabel, dramaStatusOptions } from '../../shared/labels';
import type { AiCoverGenerationAccepted, BaiduScanAccepted, BaiduScanStatus, Drama, DramaAssetSyncAccepted, DramaBackfillAiSummariesAccepted, DramaBackfillTotalMinutesResponse, DramaBatchFreshResponse, DramaCategory, DramaClientAssetSyncComplete, DramaClientAssetSyncPlan, HongguoCandidate, HongguoImportCandidateResponse, HongguoMangaSyncResponse } from '../../shared/types';
import { useAsyncData } from '../../shared/useAsyncData';
import { EpisodePlayer } from './EpisodePlayer';

type ClientSyncProgress = {
  dramaId: string;
  title?: string;
  status: 'pending' | 'running' | 'success' | 'failed';
  detail: string;
};

type HongguoPanelMode = 'manga' | 'new' | 'screening';

const HONGGUO_SYNC_TIMEOUT_MS = 180000;

export function DramasPage() {
  const [version, setVersion] = useState(0);
  const [filters, setFilters] = useState<Record<string, unknown>>({});
  const [editing, setEditing] = useState<Drama | null>(null);
  const [viewing, setViewing] = useState<Drama | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [generating, setGenerating] = useState<string | null>(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([]);
  const [syncingAssets, setSyncingAssets] = useState(false);
  const [freshing, setFreshing] = useState(false);
  const [backfillingMinutes, setBackfillingMinutes] = useState(false);
  const [backfillingAiSummaries, setBackfillingAiSummaries] = useState(false);
  const [syncModeOpen, setSyncModeOpen] = useState(false);
  const [clientSyncOpen, setClientSyncOpen] = useState(false);
  const [clientSyncItems, setClientSyncItems] = useState<ClientSyncProgress[]>([]);
  const [hongguoOpen, setHongguoOpen] = useState(false);
  const [hongguoMode, setHongguoMode] = useState<HongguoPanelMode>('manga');
  const [hongguoKeyword, setHongguoKeyword] = useState('漫剧');
  const [hongguoPage, setHongguoPage] = useState(1);
  const [hongguoNewPage, setHongguoNewPage] = useState(1);
  const hongguoScreeningPage = 1;
  const [hongguoCandidates, setHongguoCandidates] = useState<HongguoCandidate[]>([]);
  const [loadingHongguoCandidates, setLoadingHongguoCandidates] = useState(false);
  const [syncingHongguo, setSyncingHongguo] = useState(false);
  const [importingHongguoId, setImportingHongguoId] = useState<string | null>(null);
  const [form] = Form.useForm();
  const { data: categories } = useAsyncData(() => apiGet<DramaCategory[]>('/desktop/categories'));
  const { data: scanStatus } = useAsyncData(() => apiGet<BaiduScanStatus>('/admin/dramas/scan-baidu/status'), [version]);
  const selectedDramaIds = useMemo(() => selectedRowKeys.map(String), [selectedRowKeys]);
  const hasSelectedDramas = selectedDramaIds.length > 0;
  const categoryName = useMemo(
    () => new Map((categories ?? []).map((category) => [category.code, category.name])),
    [categories],
  );
  const isHongguoNewMode = hongguoMode === 'new';
  const isHongguoScreeningMode = hongguoMode === 'screening';

  async function scan() {
    await apiPost<BaiduScanAccepted>('/admin/dramas/scan-baidu', {});
    appMessage.success('已开始后台扫描，扫描成功后会更新上次扫描时间并继续生成 AI 剧名、AI 简介和封面');
    setVersion((value) => value + 1);
  }

  async function openHongguoMangaSearch() {
    setHongguoMode('manga');
    setHongguoOpen(true);
    await loadHongguoMangaCandidates(hongguoKeyword, hongguoPage);
  }

  async function openHongguoNewDramas() {
    setHongguoMode('new');
    setHongguoOpen(true);
    await loadHongguoNewCandidates(hongguoNewPage);
  }

  async function openHongguoAiMangaNewDramas() {
    setHongguoMode('screening');
    setHongguoOpen(true);
    await loadHongguoScreeningCandidates(hongguoScreeningPage);
  }

  async function loadHongguoMangaCandidates(keyword = hongguoKeyword, page = hongguoPage) {
    setLoadingHongguoCandidates(true);
    try {
      const params = new URLSearchParams();
      if (keyword.trim()) {
        params.set('keyword', keyword.trim());
      }
      params.set('page', String(Math.max(Number(page || 1), 1)));
      const query = `?${params.toString()}`;
      const rows = await apiGet<HongguoCandidate[]>(`/admin/hongguo/manga-candidates${query}`);
      setHongguoCandidates(rows);
    } finally {
      setLoadingHongguoCandidates(false);
    }
  }

  async function loadHongguoNewCandidates(page = hongguoNewPage) {
    setLoadingHongguoCandidates(true);
    try {
      const params = new URLSearchParams();
      params.set('page', String(Math.max(Number(page || 1), 1)));
      const rows = await apiGet<HongguoCandidate[]>(`/admin/hongguo/new-candidates?${params.toString()}`);
      setHongguoCandidates(rows);
    } finally {
      setLoadingHongguoCandidates(false);
    }
  }

  async function loadHongguoScreeningCandidates(page = hongguoScreeningPage) {
    setLoadingHongguoCandidates(true);
    try {
      const params = new URLSearchParams();
      params.set('page', String(Math.max(Number(page || 1), 1)));
      const rows = await apiGet<HongguoCandidate[]>(`/admin/hongguo/ai-manga-new-candidates?${params.toString()}`);
      setHongguoCandidates(rows);
    } finally {
      setLoadingHongguoCandidates(false);
    }
  }

  async function loadCurrentHongguoCandidates() {
    if (hongguoMode === 'new') {
      await loadHongguoNewCandidates(hongguoNewPage);
      return;
    }
    if (hongguoMode === 'screening') {
      await loadHongguoScreeningCandidates(hongguoScreeningPage);
      return;
    }
    await loadHongguoMangaCandidates(hongguoKeyword, hongguoPage);
  }

  async function syncHongguoMangaSearch() {
    setSyncingHongguo(true);
    try {
      const result = await apiPost<HongguoMangaSyncResponse>('/admin/hongguo/manga-sync', {
        keyword: hongguoKeyword,
        page: hongguoPage,
      }, {
        timeout: HONGGUO_SYNC_TIMEOUT_MS,
      });
      appMessage.success(`红果漫剧已同步：搜索 ${result.fetched} 部，查详情 ${result.detailed} 部，跳过 ${result.skipped} 部，新增 ${result.created} 部，更新 ${result.updated} 部`);
      await loadHongguoMangaCandidates(hongguoKeyword, hongguoPage);
    } finally {
      setSyncingHongguo(false);
    }
  }

  async function syncHongguoNewDramas() {
    setSyncingHongguo(true);
    try {
      const result = await apiPost<HongguoMangaSyncResponse>('/admin/hongguo/new-sync', {
        page: hongguoNewPage,
      }, {
        timeout: HONGGUO_SYNC_TIMEOUT_MS,
      });
      appMessage.success(`红果新剧已同步：获取 ${result.fetched} 部，查详情 ${result.detailed} 部，跳过 ${result.skipped} 部，新增 ${result.created} 部，更新 ${result.updated} 部`);
      await loadHongguoNewCandidates(hongguoNewPage);
    } finally {
      setSyncingHongguo(false);
    }
  }

  async function syncHongguoAiMangaNewDramas() {
    setSyncingHongguo(true);
    try {
      const result = await apiPost<HongguoMangaSyncResponse>('/admin/hongguo/ai-manga-new-sync', {
        page: hongguoScreeningPage,
      }, {
        timeout: HONGGUO_SYNC_TIMEOUT_MS,
      });
      appMessage.success(`AI漫剧7日上新60-120分钟已同步：获取 ${result.fetched} 部，查详情 ${result.detailed} 部，跳过 ${result.skipped} 部，新增 ${result.created} 部，更新 ${result.updated} 部`);
      await loadHongguoScreeningCandidates(hongguoScreeningPage);
    } finally {
      setSyncingHongguo(false);
    }
  }

  async function syncCurrentHongguo() {
    if (hongguoMode === 'new') {
      await syncHongguoNewDramas();
      return;
    }
    if (hongguoMode === 'screening') {
      await syncHongguoAiMangaNewDramas();
      return;
    }
    await syncHongguoMangaSearch();
  }

  async function importHongguoCandidate(candidate: HongguoCandidate) {
    setImportingHongguoId(candidate.id);
    try {
      await apiPost<HongguoImportCandidateResponse>(`/admin/hongguo/candidates/${candidate.id}/import`, {});
      appMessage.success('已导入短剧目录并加入可分发池，客户端领取时才会生成 AI 素材和下载剧集视频');
      setVersion((value) => value + 1);
      await loadCurrentHongguoCandidates();
    } finally {
      setImportingHongguoId(null);
    }
  }

  async function backfillTotalMinutes() {
    if (!hasSelectedDramas) {
      return;
    }
    setBackfillingMinutes(true);
    try {
      const result = await apiPost<DramaBackfillTotalMinutesResponse>('/admin/dramas/backfill-total-minutes', {
        ids: selectedDramaIds,
      });
      appMessage.success(`总时长已补齐：更新 ${result.updated} / ${result.requested} 条`);
      setVersion((value) => value + 1);
    } finally {
      setBackfillingMinutes(false);
    }
  }

  async function backfillAiSummaries() {
    if (!hasSelectedDramas) {
      return;
    }
    setBackfillingAiSummaries(true);
    try {
      const result = await apiPost<DramaBackfillAiSummariesAccepted>('/admin/dramas/backfill-ai-summaries', {
        ids: selectedDramaIds,
      });
      appMessage.success(`已提交 ${result.requested} 部短剧的 AI 简介补跑任务`);
      setVersion((value) => value + 1);
    } finally {
      setBackfillingAiSummaries(false);
    }
  }

  function showEditor(drama?: Drama) {
    setEditing(drama ?? null);
    form.setFieldsValue(drama ?? { categoryIds: [], status: 'DRAFT', rating: 5 });
    setEditorOpen(true);
  }

  async function submit(values: Drama) {
    const payload = {
      title: values.title,
      aiTitle: values.aiTitle,
      summary: values.summary,
      aiSummary: values.aiSummary,
      coverUrl: values.coverUrl,
      aiCoverUrl: values.aiCoverUrl,
      aiVideoCoverUrl: values.aiVideoCoverUrl,
      rating: values.rating ?? 5,
      costAmountWan: values.costAmountWan,
      categoryIds: values.categoryIds,
      status: values.status,
    };
    if (editing) {
      await apiPut(`/admin/dramas/${editing.id}`, payload);
      appMessage.success('短剧已更新');
    } else {
      await apiPost('/admin/dramas', payload);
      appMessage.success('短剧已创建');
    }
    setEditing(null);
    setEditorOpen(false);
    setVersion((value) => value + 1);
  }

  async function generateTitle(record: Drama) {
    const key = `title-${record.id}`;
    setGenerating(key);
    try {
      const updated = await apiPost<Drama>(`/admin/dramas/${record.id}/generate-title`, {});
      appMessage.success('新剧名和 AI 简介已生成');
      syncViewedDrama(updated);
      setVersion((value) => value + 1);
    } finally {
      setGenerating(null);
    }
  }

  async function generateCover(record: Drama) {
    const key = `cover-${record.id}`;
    setGenerating(key);
    try {
      await apiPost<AiCoverGenerationAccepted>(`/admin/dramas/${record.id}/generate-cover`, {});
      appMessage.success('AI 封面已开始生成，约 1 分钟后刷新查看');
      syncViewedDrama({ ...record, aiCoverGenerating: true });
      setVersion((value) => value + 1);
    } finally {
      setGenerating(null);
    }
  }

  function openSyncAssetsMode() {
    if (!hasSelectedDramas) {
      return;
    }
    setSyncModeOpen(true);
  }

  async function syncSelectedAssetsInBackend() {
    setSyncingAssets(true);
    try {
      const result = await apiPost<DramaAssetSyncAccepted>('/admin/dramas/sync-assets', {
        ids: selectedDramaIds,
      });
      appMessage.success(`已开始后台同步 ${result.requested} 部短剧，同步后会继续生成 AI 剧名、AI 简介和封面`);
      setSelectedRowKeys([]);
      setSyncModeOpen(false);
    } finally {
      setSyncingAssets(false);
    }
  }

  async function batchFreshSelected() {
    if (!hasSelectedDramas) {
      return;
    }
    setFreshing(true);
    try {
      const result = await apiPost<DramaBatchFreshResponse>('/admin/dramas/batch-fresh', {
        ids: selectedDramaIds,
      });
      appMessage.success(`已上新 ${result.updated}/${result.requested} 部短剧`);
      setSelectedRowKeys([]);
      setVersion((value) => value + 1);
    } finally {
      setFreshing(false);
    }
  }

  async function syncSelectedAssetsInBrowser() {
    const ids = selectedDramaIds;
    setSyncingAssets(true);
    setSyncModeOpen(false);
    setClientSyncOpen(true);
    try {
      const plan = await apiPost<DramaClientAssetSyncPlan>('/admin/dramas/sync-assets/client-plan', { ids });
      setClientSyncItems(plan.items.map((item) => ({
        dramaId: item.dramaId,
        title: item.title,
        status: item.errorMessage ? 'failed' : 'pending',
        detail: item.errorMessage || '等待同步',
      })));
      for (const item of plan.items) {
        if (item.errorMessage) {
          continue;
        }
        updateClientSyncItem(item.dramaId, { status: 'running', detail: '正在通过浏览器下载简介和封面' });
        try {
          const [summary, cover] = await Promise.all([
            item.summaryDownloadUrl ? downloadText(item.summaryDownloadUrl) : Promise.resolve(undefined),
            item.coverDownloadUrl ? downloadBlob(item.coverDownloadUrl) : Promise.resolve(undefined),
          ]);
          if (!summary && !cover) {
            throw new Error('没有可同步的简介或封面');
          }
          updateClientSyncItem(item.dramaId, { status: 'running', detail: '正在上传到后台保存' });
          const formData = new FormData();
          if (summary) {
            formData.append('summary', summary);
          }
          if (item.coverPath) {
            formData.append('coverPath', item.coverPath);
          }
          if (cover) {
            formData.append('cover', cover, coverFileName(item.coverPath));
          }
          await http.post<DramaClientAssetSyncComplete>(`/admin/dramas/sync-assets/client-complete/${item.dramaId}`, formData, {
            timeout: 120000,
          });
          updateClientSyncItem(item.dramaId, { status: 'success', detail: '已保存，后台会继续生成 AI 剧名、AI 简介和封面' });
        } catch (error) {
          updateClientSyncItem(item.dramaId, {
            status: 'failed',
            detail: error instanceof Error ? error.message : '浏览器同步失败',
          });
        }
      }
      appMessage.success('浏览器同步已完成');
      setSelectedRowKeys([]);
      setVersion((value) => value + 1);
    } finally {
      setSyncingAssets(false);
    }
  }

  async function downloadText(url: string) {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`简介下载失败：HTTP ${response.status}`);
    }
    return response.text();
  }

  async function downloadBlob(url: string) {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`封面下载失败：HTTP ${response.status}`);
    }
    return response.blob();
  }

  function coverFileName(path?: string) {
    const name = path?.split('/').filter(Boolean).pop();
    return name || 'cover.jpg';
  }

  function updateClientSyncItem(dramaId: string, patch: Partial<ClientSyncProgress>) {
    setClientSyncItems((items) => items.map((item) => item.dramaId === dramaId ? { ...item, ...patch } : item));
  }

  async function remove(record: Drama) {
    await apiDelete(`/admin/dramas/${record.id}`);
    appMessage.success('短剧已删除');
    setSelectedRowKeys((keys) => keys.filter((key) => key !== record.id));
    setViewing((current) => current?.id === record.id ? null : current);
    setVersion((value) => value + 1);
  }

  function syncViewedDrama(updated: Drama) {
    setViewing((current) => current?.id === updated.id ? updated : current);
  }

  function hongguoPanelTitle() {
    if (isHongguoScreeningMode) {
      return 'AI漫剧7日上新60-120分钟';
    }
    return isHongguoNewMode ? '红果新剧' : '红果漫剧搜索';
  }

  function hongguoCurrentPage() {
    if (isHongguoScreeningMode) {
      return hongguoScreeningPage;
    }
    return isHongguoNewMode ? hongguoNewPage : hongguoPage;
  }

  function hongguoSyncButtonText() {
    if (isHongguoScreeningMode) {
      return '同步AI漫剧7日上新60-120分钟';
    }
    return isHongguoNewMode ? '同步新剧' : '搜索漫剧';
  }

  function hongguoEmptyMessage() {
    if (isHongguoScreeningMode) {
      return '当前页还没有 AI漫剧7日上新60-120分钟候选';
    }
    return isHongguoNewMode ? '当前页还没有候选短剧' : '当前关键词还没有候选短剧';
  }

  function hongguoInfoMessage() {
    if (isHongguoScreeningMode) {
      return '同步近 7 日上新、60-120 分钟的 AI 漫剧候选；只请求筛选列表，导入单部时才拉详情并保存目录。';
    }
    return isHongguoNewMode
      ? '走 hg_new_play 的新剧接口；默认 date 取当前时间往前 3 小时所在日期，接口只支持按日期取新剧，不过滤真人/漫剧。每次同步会对当前页候选查详情并按发布时间倒序展示；导入单部后只保存目录，客户端下载剧集时才取链。'
      : '走 hg_new 的 mj_search 搜索漫剧；数字为页码。每次搜索会对当前页所有候选查一次详情并按发布时间倒序展示；导入单部后只保存目录，客户端下载剧集时才取链。';
  }

  function detailItem(label: string, value: ReactNode) {
    return (
      <div className="drama-detail-item">
        <span className="drama-detail-label">{label}</span>
        <div className="drama-detail-value">{value ?? '-'}</div>
      </div>
    );
  }

  return (
    <DataPage
      title="短剧管理"
      actions={(
        <>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => showEditor()}>新增短剧</Button>
          <Button icon={<CloudSyncOutlined />} onClick={scan}>扫描</Button>
          <Button icon={<SearchOutlined />} onClick={openHongguoMangaSearch}>红果漫剧搜索</Button>
          <Button icon={<CalendarOutlined />} onClick={openHongguoNewDramas}>红果新剧</Button>
          <Button icon={<RocketOutlined />} onClick={openHongguoAiMangaNewDramas}>AI漫剧7日上新60-120分钟</Button>
          <Button
            icon={<ClockCircleOutlined />}
            disabled={!hasSelectedDramas}
            loading={backfillingMinutes}
            onClick={backfillTotalMinutes}
          >
            补总时长{selectedDramaIds.length ? `（${selectedDramaIds.length}）` : ''}
          </Button>
          <Button
            icon={<FileTextOutlined />}
            disabled={!hasSelectedDramas}
            loading={backfillingAiSummaries}
            onClick={backfillAiSummaries}
          >
            补跑AI简介{selectedDramaIds.length ? `（${selectedDramaIds.length}）` : ''}
          </Button>
          <Button
            icon={<SyncOutlined />}
            disabled={!hasSelectedDramas}
            loading={syncingAssets}
            onClick={openSyncAssetsMode}
          >
            同步封面和简介{selectedDramaIds.length ? `（${selectedDramaIds.length}）` : ''}
          </Button>
          <Button
            icon={<RocketOutlined />}
            disabled={!hasSelectedDramas}
            loading={freshing}
            onClick={batchFreshSelected}
          >
            批量上新{selectedDramaIds.length ? `（${selectedDramaIds.length}）` : ''}
          </Button>
          <span className="scan-meta">上次扫描：{formatDateTime(scanStatus?.lastScanAt)}</span>
        </>
      )}
      extra={(
        <TableToolbar
          fields={[
            { name: 'keyword', placeholder: '搜索剧名/AI剧名/简介/AI简介/目录', width: 260 },
            {
              name: 'status',
              placeholder: '状态',
              type: 'select',
              options: dramaStatusOptions,
            },
            {
              name: 'assetState',
              placeholder: '素材状态',
              type: 'select',
              width: 150,
              options: [
                { value: 'MISSING_COVER', label: '无封面' },
                { value: 'MISSING_SUMMARY', label: '无简介' },
                { value: 'MISSING_AI_SUMMARY', label: '无AI简介' },
              ],
            },
            { name: 'episodeCount', placeholder: '集数', type: 'number', width: 120 },
            {
              name: 'categoryIds',
              placeholder: '分类',
              type: 'select',
              mode: 'multiple',
              width: 220,
              options: (categories ?? []).map((category) => ({ value: category.code, label: category.name })),
            },
          ]}
          onSearch={setFilters}
        />
      )}
    >
      <AdminTable<Drama>
        rowKey="id"
        scroll={{ x: 2170 }}
        tableLayout="fixed"
        reloadKey={`${version}-${JSON.stringify(filters)}`}
        loadPage={(page, size) => apiGetPage<Drama>('/admin/dramas', page, size, filters as Record<string, string | number | boolean | string[] | undefined>)}
        rowSelection={{
          selectedRowKeys,
          onChange: setSelectedRowKeys,
          preserveSelectedRowKeys: true,
        }}
        columns={[
          {
            title: '封面',
            dataIndex: 'coverUrl',
            width: 90,
            render: (coverUrl?: string) => coverUrl ? <Image className="drama-cover" src={coverUrl} alt="短剧封面" /> : <span className="muted">无封面</span>,
          },
          {
            title: 'AI封面',
            dataIndex: 'aiCoverUrl',
            width: 90,
            render: (aiCoverUrl?: string) => aiCoverUrl ? <Image className="drama-cover" src={aiCoverUrl} alt="AI封面" /> : <span className="muted">未生成</span>,
          },
          { title: '短剧名称', dataIndex: 'title', width: 220 },
          {
            title: 'AI 剧名',
            dataIndex: 'aiTitle',
            width: 160,
            render: (aiTitle?: string) => aiTitle || <span className="muted">未生成</span>,
          },
          {
            title: '简介',
            dataIndex: 'summary',
            width: 320,
            render: (summary?: string) => (
              <Typography.Paragraph className="table-summary" ellipsis={{ rows: 2, tooltip: summary }}>
                {summary || '-'}
              </Typography.Paragraph>
            ),
          },
          {
            title: 'AI 简介',
            dataIndex: 'aiSummary',
            width: 320,
            render: (aiSummary?: string) => (
              <Typography.Paragraph className="table-summary" ellipsis={{ rows: 2, tooltip: aiSummary }}>
                {aiSummary || <span className="muted">未生成</span>}
              </Typography.Paragraph>
            ),
          },
          {
            title: '分类',
            dataIndex: 'categoryIds',
            width: 260,
            render: (ids: string[]) => ids?.map((id) => <Tag key={id}>{categoryName.get(id) ?? id}</Tag>),
          },
          { title: '评分', dataIndex: 'rating', width: 80, render: (rating?: number) => `${rating ?? 5}分` },
          { title: '集数', dataIndex: 'episodes', width: 80, render: (episodes: Drama['episodes']) => episodes?.length ?? 0 },
          { title: '总时长', dataIndex: 'totalMinutes', width: 90, render: (value?: number) => value ? `${value} 分钟` : '-' },
          { title: '成本金额', dataIndex: 'costAmountWan', width: 100, render: (value?: number) => value ? `${value} 万` : '-' },
          { title: '创建时间', dataIndex: 'createdAt', width: 180, render: formatDateTime },
          {
            title: '状态',
            dataIndex: 'status',
            width: 100,
            render: (status: Drama['status']) => <Tag color={dramaStatusColors[status]}>{dramaStatusLabel(status)}</Tag>,
          },
          {
            title: '操作',
            width: 220,
            fixed: 'right',
            render: (_, record) => (
              <Space size={4}>
                <Tooltip title="详情">
                  <Button className="table-action" size="small" type="text" icon={<InfoCircleOutlined />} onClick={() => setViewing(record)} />
                </Tooltip>
                <Tooltip title="编辑">
                  <Button className="table-action" size="small" type="text" icon={<EditOutlined />} onClick={() => showEditor(record)} />
                </Tooltip>
                <Tooltip title="生成新剧名和 AI 简介">
                  <Button
                    className="table-action"
                    size="small"
                    type="text"
                    icon={<FileTextOutlined />}
                    loading={generating === `title-${record.id}`}
                    onClick={() => generateTitle(record)}
                  />
                </Tooltip>
                <Tooltip title={record.aiCoverGenerating ? 'AI 封面生成中' : '生成新封面'}>
                  <Button
                    className="table-action"
                    size="small"
                    type="text"
                    icon={<PictureOutlined />}
                    loading={generating === `cover-${record.id}` || record.aiCoverGenerating}
                    disabled={record.aiCoverGenerating}
                    onClick={() => generateCover(record)}
                  />
                </Tooltip>
                <Popconfirm title="删除这个短剧？" onConfirm={() => remove(record)}>
                  <Tooltip title="删除">
                    <Button className="table-action" size="small" type="text" danger icon={<DeleteOutlined />} />
                  </Tooltip>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />
      <Drawer
        title="短剧详情"
        width="min(94vw, 920px)"
        open={!!viewing}
        onClose={() => setViewing(null)}
        destroyOnClose
      >
        {viewing ? (
          <div className="drama-detail">
            <div className="drama-detail-hero">
              <div className="drama-detail-cover-frame">
                {viewing.coverUrl ? (
                  <Image className="drama-detail-cover" src={viewing.coverUrl} alt="原始封面" />
                ) : (
                  <div className="drama-detail-cover-empty">无封面</div>
                )}
              </div>
              <div className="drama-detail-heading">
                <div className="drama-detail-title-row">
                  <Typography.Title level={3}>{viewing.title}</Typography.Title>
                  <Tag color={dramaStatusColors[viewing.status]}>{dramaStatusLabel(viewing.status)}</Tag>
                </div>
                <div className="drama-detail-subtitle">{viewing.aiTitle ? `AI 新剧名：${viewing.aiTitle}` : 'AI 新剧名：未生成'}</div>
                <div className="drama-detail-tags">
                  {viewing.categoryIds?.length
                    ? viewing.categoryIds.map((id) => <Tag key={id}>{categoryName.get(id) ?? id}</Tag>)
                    : <span className="muted">未分类</span>}
                </div>
              </div>
            </div>

            <section className="drama-detail-section">
              <h3>基础信息</h3>
              <div className="drama-detail-grid">
                {detailItem('集数', viewing.episodes?.length ?? 0)}
                {detailItem('总时长', viewing.totalMinutes ? `${viewing.totalMinutes} 分钟` : '-')}
                {detailItem('成本金额', viewing.costAmountWan ? `${viewing.costAmountWan} 万` : '-')}
                {detailItem('评分', `${viewing.rating ?? 5}分`)}
                {detailItem('创建时间', formatDateTime(viewing.createdAt))}
                {detailItem('更新时间', formatDateTime(viewing.updatedAt))}
                {detailItem('来源目录', <Typography.Text copyable className="mono-id">{viewing.sourcePath || '-'}</Typography.Text>)}
              </div>
            </section>

            <section className="drama-detail-section">
              <h3>简介</h3>
              <Typography.Paragraph className="drama-detail-summary">
                {viewing.summary || '-'}
              </Typography.Paragraph>
            </section>

            <section className="drama-detail-section">
              <h3>AI 简介</h3>
              <Typography.Paragraph className="drama-detail-summary">
                {viewing.aiSummary || '-'}
              </Typography.Paragraph>
            </section>

            <section className="drama-detail-section">
              <h3>封面</h3>
              <div className="drama-cover-pair">
                <div className="drama-cover-preview">
                  <span>原始封面</span>
                  {viewing.coverUrl ? <Image className="drama-detail-cover-small" src={viewing.coverUrl} alt="原始封面" /> : <div className="drama-cover-placeholder">无封面</div>}
                </div>
                <div className="drama-cover-preview">
                  <span>
                    AI 新封面
                    {viewing.aiCoverGenerating ? <Tag color="processing">生成中</Tag> : null}
                  </span>
                  {viewing.aiCoverGenerating ? (
                    <div className="drama-cover-placeholder">
                      <Spin size="small" />
                      <span>AI 封面生成中，约 1 分钟后刷新查看</span>
                    </div>
                  ) : viewing.aiCoverUrl ? (
                    <Image className="drama-detail-cover-small" src={viewing.aiCoverUrl} alt="AI 新封面" />
                  ) : (
                    <div className="drama-cover-placeholder">未生成</div>
                  )}
                </div>
                <div className="drama-cover-preview">
                  <span>横版视频封面</span>
                  {viewing.aiVideoCoverUrl ? (
                    <Image className="drama-detail-cover-small" src={viewing.aiVideoCoverUrl} alt="横版视频封面" />
                  ) : (
                    <div className="drama-cover-placeholder">未生成</div>
                  )}
                </div>
              </div>
            </section>

            <section className="drama-detail-section">
              <h3>剧集播放</h3>
              <EpisodePlayer dramaId={viewing.id} />
            </section>
          </div>
        ) : null}
      </Drawer>
      <Modal
        title="选择同步方式"
        open={syncModeOpen}
        onCancel={() => setSyncModeOpen(false)}
        footer={null}
        destroyOnClose
      >
        <Space direction="vertical" size={16} className="asset-sync-mode">
          <div className="asset-sync-mode-list">
            <button type="button" className="asset-sync-mode-card" onClick={syncSelectedAssetsInBrowser}>
              <span className="asset-sync-mode-dot" />
              <span>
                <strong>浏览器端同步</strong>
                <em>使用当前浏览器网络下载百度封面和简介，再上传到后台。</em>
              </span>
            </button>
            <button type="button" className="asset-sync-mode-card" onClick={syncSelectedAssetsInBackend}>
              <span className="asset-sync-mode-dot" />
              <span>
                <strong>后台同步</strong>
                <em>继续由 AWS 后台下载，适合少量或网络稳定时使用。</em>
              </span>
            </button>
          </div>
          <Alert
            type="warning"
            showIcon
            message="浏览器端同步请确保当前网络在中国大陆"
            description="如果百度下载链接不允许跨域访问，进度里会显示失败原因；这种情况下可以改用后台同步或换本地辅助工具。"
          />
        </Space>
      </Modal>
      <Modal
        title="浏览器端同步进度"
        open={clientSyncOpen}
        onCancel={() => setClientSyncOpen(false)}
        footer={[
          <Button key="close" onClick={() => setClientSyncOpen(false)} disabled={syncingAssets}>关闭</Button>,
        ]}
        width={760}
      >
        <Space direction="vertical" size={16} className="client-sync-progress">
          <Alert type="info" showIcon message="同步期间请保持这个页面打开，浏览器会逐部下载并上传到后台。" />
          <Progress
            percent={clientSyncItems.length ? Math.round((clientSyncItems.filter((item) => item.status === 'success' || item.status === 'failed').length / clientSyncItems.length) * 100) : 0}
            status={clientSyncItems.some((item) => item.status === 'failed') ? 'exception' : syncingAssets ? 'active' : 'success'}
          />
          <div className="client-sync-list">
            {clientSyncItems.map((item) => (
              <div key={item.dramaId} className="client-sync-row">
                <div>
                  <strong>{item.title || item.dramaId}</strong>
                  <span>{item.detail}</span>
                </div>
                <Tag color={item.status === 'success' ? 'green' : item.status === 'failed' ? 'red' : item.status === 'running' ? 'processing' : 'default'}>
                  {item.status === 'success' ? '完成' : item.status === 'failed' ? '失败' : item.status === 'running' ? '同步中' : '等待'}
                </Tag>
              </div>
            ))}
          </div>
        </Space>
      </Modal>
      <Modal
        title={hongguoPanelTitle()}
        open={hongguoOpen}
        onCancel={() => setHongguoOpen(false)}
        footer={[
          <Button key="refresh" onClick={loadCurrentHongguoCandidates} loading={loadingHongguoCandidates}>刷新</Button>,
          <Button key="close" type="primary" onClick={() => setHongguoOpen(false)}>关闭</Button>,
        ]}
        width={980}
        destroyOnClose
      >
        <Space direction="vertical" size={16} className="hongguo-calendar">
          <Space wrap>
            {isHongguoNewMode || isHongguoScreeningMode ? null : (
              <Input
                value={hongguoKeyword}
                onChange={(event) => setHongguoKeyword(event.target.value)}
                onBlur={() => loadHongguoMangaCandidates(hongguoKeyword, hongguoPage)}
                className="hongguo-keyword-input"
                placeholder="搜索关键词"
              />
            )}
            {isHongguoScreeningMode ? null : (
              <InputNumber
                min={1}
                precision={0}
                value={hongguoCurrentPage()}
                onChange={(value) => {
                  const page = Number(value || 1);
                  if (isHongguoNewMode) {
                    setHongguoNewPage(page);
                  } else {
                    setHongguoPage(page);
                  }
                }}
              />
            )}
            <Button
              type="primary"
              icon={isHongguoScreeningMode ? <RocketOutlined /> : isHongguoNewMode ? <CalendarOutlined /> : <SearchOutlined />}
              loading={syncingHongguo}
              onClick={syncCurrentHongguo}
            >
              {hongguoSyncButtonText()}
            </Button>
          </Space>
          <Alert
            type="info"
            showIcon
            message={hongguoInfoMessage()}
          />
          <Spin spinning={loadingHongguoCandidates}>
            {hongguoCandidates.length ? (
              <div className="hongguo-candidate-list">
                {hongguoCandidates.map((candidate) => (
                  <div key={candidate.id} className="hongguo-candidate-row">
                    <div className="hongguo-candidate-cover">
                      {candidate.coverUrl ? <Image src={candidate.coverUrl} alt={candidate.title} /> : <span>无封面</span>}
                    </div>
                    <div className="hongguo-candidate-main">
                      <div className="hongguo-candidate-title">
                        <strong>{candidate.title}</strong>
                        <Tag color={candidate.status === 'IMPORTED' ? 'green' : 'blue'}>
                          {candidate.status === 'IMPORTED' ? '已导入' : '候选'}
                        </Tag>
                      </div>
                      <Typography.Paragraph className="hongguo-candidate-summary" ellipsis={{ rows: 2, tooltip: candidate.summary }}>
                        {candidate.summary || '-'}
                      </Typography.Paragraph>
                      <Space wrap size={[4, 4]}>
                        <Tag color={candidate.publishedAt ? 'purple' : 'default'}>
                          发布时间：{candidate.publishedAt ? formatDateTime(candidate.publishedAt) : '未返回'}
                        </Tag>
                        {candidate.category ? <Tag>{candidate.category}</Tag> : null}
                        {candidate.categories?.map((category) => <Tag key={category}>{category}</Tag>)}
                        <Tag>{candidate.episodeCount || 0} 集</Tag>
                        {candidate.duration ? <Tag>{candidate.duration}</Tag> : null}
                        {candidate.score ? <Tag>{candidate.score} 分</Tag> : null}
                      </Space>
                    </div>
                    <div className="hongguo-candidate-actions">
                      <Button
                        type="primary"
                        disabled={candidate.status === 'IMPORTED'}
                        loading={importingHongguoId === candidate.id}
                        onClick={() => importHongguoCandidate(candidate)}
                      >
                        导入
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <Alert type="warning" showIcon message={hongguoEmptyMessage()} />
            )}
          </Spin>
        </Space>
      </Modal>
      <Modal
        title={editing ? '编辑短剧' : '新增短剧'}
        open={editorOpen}
        onCancel={() => {
          setEditorOpen(false);
          setEditing(null);
        }}
        onOk={() => form.submit()}
        width={720}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={submit}>
          <Form.Item name="title" label="剧名" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="aiTitle" label="AI 新剧名">
            <Input />
          </Form.Item>
          <Form.Item name="summary" label="简介">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="aiSummary" label="AI 简介">
            <Input.TextArea rows={3} maxLength={100} showCount />
          </Form.Item>
          <Form.Item name="coverUrl" label="封面地址">
            <Input />
          </Form.Item>
          <Form.Item name="aiCoverUrl" label="AI 新封面地址">
            <Input />
          </Form.Item>
          <Form.Item name="aiVideoCoverUrl" label="横版视频封面地址">
            <Input />
          </Form.Item>
          <Form.Item name="rating" label="评分" rules={[{ required: true }]}>
            <InputNumber min={1} max={5} precision={0} />
          </Form.Item>
          <Form.Item name="costAmountWan" label="成本金额（万）">
            <InputNumber min={1} max={99} precision={0} placeholder="不填则自动生成" />
          </Form.Item>
          <Form.Item name="categoryIds" label="分类">
            <Select
              mode="multiple"
              options={(categories ?? []).map((category) => ({ value: category.code, label: category.name }))}
            />
          </Form.Item>
          <Form.Item name="status" label="状态" rules={[{ required: true }]}>
            <Select options={dramaStatusOptions} />
          </Form.Item>
        </Form>
      </Modal>
    </DataPage>
  );
}
