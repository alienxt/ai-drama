import { CloudSyncOutlined, DeleteOutlined, EditOutlined, FileTextOutlined, InfoCircleOutlined, PictureOutlined, PlusOutlined, SyncOutlined } from '@ant-design/icons';
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
import type { AiCoverGenerationAccepted, BaiduScanAccepted, BaiduScanStatus, Drama, DramaAssetSyncAccepted, DramaCategory, DramaClientAssetSyncComplete, DramaClientAssetSyncPlan } from '../../shared/types';
import { useAsyncData } from '../../shared/useAsyncData';
import { EpisodePlayer } from './EpisodePlayer';

type ClientSyncProgress = {
  dramaId: string;
  title?: string;
  status: 'pending' | 'running' | 'success' | 'failed';
  detail: string;
};

export function DramasPage() {
  const [version, setVersion] = useState(0);
  const [filters, setFilters] = useState<Record<string, unknown>>({});
  const [editing, setEditing] = useState<Drama | null>(null);
  const [viewing, setViewing] = useState<Drama | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [generating, setGenerating] = useState<string | null>(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([]);
  const [syncingAssets, setSyncingAssets] = useState(false);
  const [syncModeOpen, setSyncModeOpen] = useState(false);
  const [clientSyncOpen, setClientSyncOpen] = useState(false);
  const [clientSyncItems, setClientSyncItems] = useState<ClientSyncProgress[]>([]);
  const [form] = Form.useForm();
  const { data: categories } = useAsyncData(() => apiGet<DramaCategory[]>('/desktop/categories'));
  const { data: scanStatus } = useAsyncData(() => apiGet<BaiduScanStatus>('/admin/dramas/scan-baidu/status'), [version]);
  const categoryName = useMemo(
    () => new Map((categories ?? []).map((category) => [category.code, category.name])),
    [categories],
  );

  async function scan() {
    await apiPost<BaiduScanAccepted>('/admin/dramas/scan-baidu', {});
    appMessage.success('已开始后台扫描，扫描成功后会更新上次扫描时间并继续生成 AI 剧名和封面');
    setVersion((value) => value + 1);
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
      coverUrl: values.coverUrl,
      aiCoverUrl: values.aiCoverUrl,
      rating: values.rating ?? 5,
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
      appMessage.success('新剧名已生成');
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
    if (!selectedRowKeys.length) {
      return;
    }
    setSyncModeOpen(true);
  }

  async function syncSelectedAssetsInBackend() {
    setSyncingAssets(true);
    try {
      const result = await apiPost<DramaAssetSyncAccepted>('/admin/dramas/sync-assets', {
        ids: selectedRowKeys.map(String),
      });
      appMessage.success(`已开始后台同步 ${result.requested} 部短剧，同步后会继续生成 AI 剧名和封面`);
      setSelectedRowKeys([]);
      setSyncModeOpen(false);
    } finally {
      setSyncingAssets(false);
    }
  }

  async function syncSelectedAssetsInBrowser() {
    const ids = selectedRowKeys.map(String);
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
          updateClientSyncItem(item.dramaId, { status: 'success', detail: '已保存，后台会继续生成 AI 剧名和封面' });
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
          <Button
            icon={<SyncOutlined />}
            disabled={!selectedRowKeys.length}
            loading={syncingAssets}
            onClick={openSyncAssetsMode}
          >
            同步封面和简介{selectedRowKeys.length ? `（${selectedRowKeys.length}）` : ''}
          </Button>
          <span className="scan-meta">上次扫描：{formatDateTime(scanStatus?.lastScanAt)}</span>
        </>
      )}
      extra={(
        <TableToolbar
          fields={[
            { name: 'keyword', placeholder: '搜索剧名/AI剧名/简介/目录', width: 240 },
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
        scroll={{ x: 1570 }}
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
            title: '分类',
            dataIndex: 'categoryIds',
            width: 260,
            render: (ids: string[]) => ids?.map((id) => <Tag key={id}>{categoryName.get(id) ?? id}</Tag>),
          },
          { title: '评分', dataIndex: 'rating', width: 80, render: (rating?: number) => `${rating ?? 5}分` },
          { title: '集数', dataIndex: 'episodes', width: 80, render: (episodes: Drama['episodes']) => episodes?.length ?? 0 },
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
                <Tooltip title="生成新剧名">
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
          <Form.Item name="coverUrl" label="封面地址">
            <Input />
          </Form.Item>
          <Form.Item name="aiCoverUrl" label="AI 新封面地址">
            <Input />
          </Form.Item>
          <Form.Item name="rating" label="评分" rules={[{ required: true }]}>
            <InputNumber min={1} max={5} precision={0} />
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
