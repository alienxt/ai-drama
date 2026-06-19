import { EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, DatePicker, Form, Input, InputNumber, Modal, Space, Switch, Tag, Tooltip } from 'antd';
import dayjs from 'dayjs';
import { useState } from 'react';
import { AdminTable } from '../../components/AdminTable';
import { DataPage } from '../../components/DataPage';
import { appMessage } from '../../shared/appMessage';
import { apiGetPage, apiPost, apiPut } from '../../shared/http';
import type { DownloadInvite } from '../../shared/types';

type InviteForm = {
  code?: string;
  note?: string;
  enabled: boolean;
  maxUses: number;
  expiresAt?: dayjs.Dayjs | null;
};

function randomCode() {
  const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  return Array.from({ length: 8 }, () => alphabet[Math.floor(Math.random() * alphabet.length)]).join('');
}

function formatDateTime(value?: string) {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '-';
}

export function DownloadInvitesPage() {
  const [reload, setReload] = useState(0);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<DownloadInvite | null>(null);
  const [form] = Form.useForm<InviteForm>();

  function showCreate() {
    setEditing(null);
    form.setFieldsValue({ code: randomCode(), enabled: true, maxUses: 1, expiresAt: null, note: '' });
    setOpen(true);
  }

  function showEditor(record: DownloadInvite) {
    setEditing(record);
    form.setFieldsValue({
      code: record.code,
      note: record.note,
      enabled: record.enabled,
      maxUses: record.maxUses,
      expiresAt: record.expiresAt ? dayjs(record.expiresAt) : null,
    });
    setOpen(true);
  }

  async function submit(values: InviteForm) {
    const payload = {
      ...values,
      code: values.code?.trim(),
      expiresAt: values.expiresAt ? values.expiresAt.toISOString() : null,
    };
    if (editing) {
      await apiPut(`/admin/download-invites/${editing.id}`, payload);
      appMessage.success('邀请码已更新');
    } else {
      await apiPost('/admin/download-invites', payload);
      appMessage.success('邀请码已创建');
    }
    setOpen(false);
    setReload((value) => value + 1);
  }

  async function toggleEnabled(record: DownloadInvite) {
    await apiPut(`/admin/download-invites/${record.id}`, {
      code: record.code,
      note: record.note,
      enabled: !record.enabled,
      maxUses: record.maxUses,
      expiresAt: record.expiresAt ?? null,
    });
    appMessage.success(record.enabled ? '邀请码已停用' : '邀请码已启用');
    setReload((value) => value + 1);
  }

  return (
    <DataPage
      title="下载邀请码"
      actions={<Button type="primary" icon={<PlusOutlined />} onClick={showCreate}>创建邀请码</Button>}
    >
      <AdminTable<DownloadInvite>
        rowKey="id"
        reloadKey={reload}
        loadPage={(page, size) => apiGetPage<DownloadInvite>('/admin/download-invites', page, size)}
        columns={[
          { title: '邀请码', dataIndex: 'code', render: (code: string) => <Tag color="blue">{code}</Tag> },
          { title: '备注', dataIndex: 'note', render: (note?: string) => note || '-' },
          {
            title: '状态',
            dataIndex: 'enabled',
            render: (enabled: boolean) => enabled ? <Tag color="green">启用</Tag> : <Tag color="default">停用</Tag>,
          },
          {
            title: '使用次数',
            render: (_, record) => `${record.usedCount}/${record.maxUses || '不限'}`,
          },
          { title: '过期时间', dataIndex: 'expiresAt', render: formatDateTime },
          { title: '最后使用', dataIndex: 'lastUsedAt', render: formatDateTime },
          {
            title: '操作',
            render: (_, record) => (
              <Space size={4}>
                <Tooltip title="编辑">
                  <Button className="table-action" size="small" type="text" icon={<EditOutlined />} onClick={() => showEditor(record)} />
                </Tooltip>
                <Tooltip title={record.enabled ? '停用' : '启用'}>
                  <Button className="table-action" size="small" type="text" icon={<ReloadOutlined />} onClick={() => toggleEnabled(record)} />
                </Tooltip>
              </Space>
            ),
          },
        ]}
      />
      <Modal
        title={editing ? '编辑邀请码' : '创建邀请码'}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={submit}>
          <Form.Item name="code" label="邀请码" rules={[{ required: true }]}>
            <Input
              placeholder="DRAMA2026"
              addonAfter={<Button type="link" size="small" onClick={() => form.setFieldValue('code', randomCode())}>换一个</Button>}
            />
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input placeholder="投放渠道或客户名称" />
          </Form.Item>
          <Form.Item name="maxUses" label="最大使用次数" tooltip="填 0 表示不限次数" rules={[{ required: true }]}>
            <InputNumber min={0} precision={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="expiresAt" label="过期时间">
            <DatePicker showTime style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="enabled" label="启用状态" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </DataPage>
  );
}
