import { DeleteOutlined, ExportOutlined, PauseCircleOutlined, PlayCircleOutlined, PlusOutlined, SettingOutlined } from '@ant-design/icons';
import { Button, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Switch, Tag, Tooltip } from 'antd';
import { useMemo, useState } from 'react';
import { AdminTable } from '../../components/AdminTable';
import { DataPage } from '../../components/DataPage';
import { TableToolbar } from '../../components/TableToolbar';
import { appMessage } from '../../shared/appMessage';
import { formatDateTime } from '../../shared/format';
import { apiDelete, apiGet, apiGetPage, apiPatch, apiPost, apiPut } from '../../shared/http';
import {
  mediaAccountStatusColors,
  mediaAccountStatusLabel,
  mediaAccountStatusOptions,
  mediaPlatformLabel,
  mediaPlatformOptions,
} from '../../shared/labels';
import type { DramaCategory, MediaAccount } from '../../shared/types';
import { useAsyncData } from '../../shared/useAsyncData';

export function MediaAccountsPage() {
  const [version, setVersion] = useState(0);
  const [filters, setFilters] = useState<Record<string, unknown>>({});
  const [editing, setEditing] = useState<MediaAccount | null>(null);
  const [creating, setCreating] = useState(false);
  const [form] = Form.useForm();
  const [createForm] = Form.useForm();
  const { data: categories } = useAsyncData(() => apiGet<DramaCategory[]>('/desktop/categories'));
  const categoryName = useMemo(
    () => new Map((categories ?? []).map((category) => [category.code, category.name])),
    [categories],
  );

  function showPolicy(account: MediaAccount) {
    setEditing(account);
    form.setFieldsValue(account.distributionPolicy ?? {});
  }

  async function submitPolicy(values: MediaAccount['distributionPolicy']) {
    if (!editing) return;
    await apiPut(`/admin/media-accounts/${editing.id}/policy`, values);
    appMessage.success('分发策略已保存');
    setEditing(null);
    setVersion((value) => value + 1);
  }

  async function create(values: Pick<MediaAccount, 'platform' | 'displayName' | 'externalAccountId' | 'deviceId'>) {
    await apiPost('/admin/media-accounts', values);
    appMessage.success('媒体号已创建');
    setCreating(false);
    createForm.resetFields();
    setVersion((value) => value + 1);
  }

  async function setDistributionStatus(account: MediaAccount, status: 'ACTIVE' | 'PAUSED') {
    await apiPatch(`/admin/media-accounts/${account.id}/status`, { status });
    appMessage.success(status === 'PAUSED' ? '已暂停该媒体号分发' : '已恢复该媒体号分发');
    setVersion((value) => value + 1);
  }

  async function remove(account: MediaAccount) {
    await apiDelete(`/admin/media-accounts/${account.id}`);
    appMessage.success('媒体号已删除');
    setVersion((value) => value + 1);
  }

  async function openBrowser(account: MediaAccount) {
    try {
      const params = new URLSearchParams({ platform: account.platform, accountId: account.id });
      await fetch(`http://127.0.0.1:17888/open-media?${params.toString()}`);
      appMessage.success('已通知桌面端打开浏览器');
    } catch {
      appMessage.error('请先在桌面端运行 aidrama-desktop agent');
    }
  }

  return (
    <DataPage
      title="媒体号管理"
      actions={<Button type="primary" icon={<PlusOutlined />} onClick={() => setCreating(true)}>新增媒体号</Button>}
      extra={(
        <TableToolbar
          fields={[
            { name: 'keyword', placeholder: '搜索名称/ID/设备' },
            {
              name: 'platform',
              placeholder: '平台',
              type: 'select',
              options: mediaPlatformOptions,
            },
            {
              name: 'status',
              placeholder: '状态',
              type: 'select',
              options: mediaAccountStatusOptions,
            },
          ]}
          onSearch={setFilters}
        />
      )}
    >
      <AdminTable<MediaAccount>
        rowKey="id"
        reloadKey={`${version}-${JSON.stringify(filters)}`}
        loadPage={(page, size) => apiGetPage<MediaAccount>('/admin/media-accounts', page, size, filters as Record<string, string | number | boolean | string[] | undefined>)}
        columns={[
          { title: '名称', dataIndex: 'displayName' },
          { title: '媒体号ID', dataIndex: 'externalAccountId', render: (value?: string) => value || '-' },
          {
            title: '平台',
            dataIndex: 'platform',
            render: (value: string) => <Tag color={value === 'WECHAT_VIDEO' ? 'green' : 'blue'}>{mediaPlatformLabel(value)}</Tag>,
          },
          {
            title: '状态',
            dataIndex: 'status',
            render: (status: MediaAccount['status']) => <Tag color={mediaAccountStatusColors[status]}>{mediaAccountStatusLabel(status)}</Tag>,
          },
          {
            title: '分发',
            dataIndex: 'status',
            render: (status: MediaAccount['status']) => (
              status === 'PAUSED'
                ? <Tag>暂停分发</Tag>
                : status === 'ACTIVE'
                  ? <Tag color="green">参与分发</Tag>
                  : <Tag color="orange">不可分发</Tag>
            ),
          },
          { title: '设备', dataIndex: 'deviceId' },
          { title: '创建时间', dataIndex: 'createdAt', width: 180, render: formatDateTime },
          { title: '登录态', dataIndex: 'loginStateRef', render: (value?: string) => value ? <Tag color="green">已保存</Tag> : <Tag>未保存</Tag> },
          { title: '每日上限', dataIndex: ['distributionPolicy', 'dailyLimit'] },
          { title: '间隔分钟', dataIndex: ['distributionPolicy', 'intervalMinutes'] },
          {
            title: '分类',
            dataIndex: ['distributionPolicy', 'categoryIds'],
            render: (ids?: string[]) => ids?.map((id) => <Tag key={id}>{categoryName.get(id) ?? id}</Tag>) ?? '-',
          },
          {
            title: '操作',
            render: (_, record) => (
              <Space size={4}>
                <Tooltip title="分发策略">
                  <Button className="table-action" size="small" type="text" icon={<SettingOutlined />} onClick={() => showPolicy(record)} />
                </Tooltip>
                {record.status === 'PAUSED' ? (
                  <Tooltip title={record.loginStateRef ? '恢复分发' : '未保存登录态，不能恢复'}>
                    <Button
                      className="table-action"
                      size="small"
                      type="text"
                      disabled={!record.loginStateRef}
                      icon={<PlayCircleOutlined />}
                      onClick={() => setDistributionStatus(record, 'ACTIVE')}
                    />
                  </Tooltip>
                ) : (
                  <Tooltip title="暂停分发">
                    <Button
                      className="table-action"
                      size="small"
                      type="text"
                      disabled={record.status !== 'ACTIVE'}
                      icon={<PauseCircleOutlined />}
                      onClick={() => setDistributionStatus(record, 'PAUSED')}
                    />
                  </Tooltip>
                )}
                <Tooltip title="打开浏览器">
                  <Button className="table-action" size="small" type="text" icon={<ExportOutlined />} onClick={() => openBrowser(record)} />
                </Tooltip>
                <Popconfirm title="删除这个媒体号？" onConfirm={() => remove(record)}>
                  <Tooltip title="删除">
                    <Button className="table-action" size="small" type="text" danger icon={<DeleteOutlined />} />
                  </Tooltip>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />
      <Modal title="媒体号分发策略" open={!!editing} onCancel={() => setEditing(null)} onOk={() => form.submit()} destroyOnClose>
        <Form
          form={form}
          layout="vertical"
          onFinish={submitPolicy}
          initialValues={{ enabled: true, dailyLimit: 3, intervalMinutes: 120, transcodePreset: 'wechat-video-default' }}
        >
          <Form.Item name="categoryIds" label="短剧类别">
            <Select
              mode="multiple"
              options={(categories ?? []).map((category) => ({ value: category.code, label: category.name }))}
            />
          </Form.Item>
          <Form.Item name="dailyLimit" label="每日最多分发">
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="intervalMinutes" label="处理间隔分钟">
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="transcodePreset" label="转码预设">
            <Select options={[{ value: 'wechat-video-default', label: '视频号默认' }]} />
          </Form.Item>
          <Form.Item name="enabled" label="启用策略" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
      <Modal title="新增媒体号" open={creating} onCancel={() => setCreating(false)} onOk={() => createForm.submit()} destroyOnClose>
        <Form form={createForm} layout="vertical" onFinish={create} initialValues={{ platform: 'WECHAT_VIDEO' }}>
          <Form.Item name="displayName" label="名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="externalAccountId" label="媒体号ID">
            <Input />
          </Form.Item>
          <Form.Item name="platform" label="平台" rules={[{ required: true }]}>
            <Select options={mediaPlatformOptions} />
          </Form.Item>
          <Form.Item name="deviceId" label="设备">
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </DataPage>
  );
}
