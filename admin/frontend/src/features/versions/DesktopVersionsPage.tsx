import {
  CloudUploadOutlined,
  DownloadOutlined,
  EditOutlined,
  PlusOutlined,
  RocketOutlined,
  StopOutlined,
} from '@ant-design/icons';
import { Button, Form, Input, Modal, Progress, Select, Space, Switch, Tag, Tooltip, Upload } from 'antd';
import type { UploadRequestOption } from 'rc-upload/lib/interface';
import { useState } from 'react';
import { AdminTable } from '../../components/AdminTable';
import { DataPage } from '../../components/DataPage';
import { appMessage } from '../../shared/appMessage';
import { apiGetPage, apiPatch, apiPost, http } from '../../shared/http';
import type { DesktopVersion } from '../../shared/types';

type VersionForm = Pick<DesktopVersion, 'platform' | 'version' | 'releaseNotes' | 'mandatory'>;

function formatSize(size: number) {
  if (!size) return '-';
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

export function DesktopVersionsPage() {
  const [reload, setReload] = useState(0);
  const [open, setOpen] = useState(false);
  const [uploadingVersionId, setUploadingVersionId] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [form] = Form.useForm<VersionForm>();

  function showCreate() {
    form.setFieldsValue({ platform: 'MAC', mandatory: false });
    setOpen(true);
  }

  async function submit(values: VersionForm) {
    await apiPost('/admin/desktop-versions', values);
    appMessage.success('版本已创建');
    setOpen(false);
    setReload((value) => value + 1);
  }

  async function setPublished(record: DesktopVersion, published: boolean) {
    await apiPatch(`/admin/desktop-versions/${record.id}/published`, { published });
    appMessage.success(published ? '版本已发布' : '版本已下架');
    setReload((value) => value + 1);
  }

  async function uploadPackage(record: DesktopVersion, options: UploadRequestOption) {
    const data = new FormData();
    data.append('file', options.file as File);
    setUploadingVersionId(record.id);
    setUploadProgress(0);
    try {
      await http.post(`/admin/desktop-versions/${record.id}/package`, data, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 30 * 60 * 1000,
        onUploadProgress: (event) => {
          if (event.total) {
            const percent = Math.round((event.loaded / event.total) * 100);
            setUploadProgress(percent);
            options.onProgress?.({ percent });
          }
        },
      });
      options.onSuccess?.({}, new XMLHttpRequest());
      appMessage.success('安装包已上传');
      setReload((value) => value + 1);
    } catch (error) {
      options.onError?.(error as Error);
    } finally {
      setUploadingVersionId(null);
      setUploadProgress(0);
    }
  }

  return (
    <DataPage
      title="桌面版本"
      actions={<Button type="primary" icon={<PlusOutlined />} onClick={showCreate}>创建版本</Button>}
    >
      <AdminTable<DesktopVersion>
        rowKey="id"
        reloadKey={reload}
        loadPage={(page, size) => apiGetPage<DesktopVersion>('/admin/desktop-versions', page, size)}
        columns={[
          { title: '平台', dataIndex: 'platform', render: (platform: DesktopVersion['platform']) => <Tag>{platform === 'MAC' ? 'macOS' : 'Windows'}</Tag> },
          { title: '版本', dataIndex: 'version' },
          { title: '更新说明', dataIndex: 'releaseNotes', ellipsis: true },
          { title: '安装包', dataIndex: 'fileName', render: (_, record) => record.downloadUrl ? <a href={record.downloadUrl} target="_blank" rel="noreferrer">{record.fileName}</a> : '-' },
          { title: '大小', dataIndex: 'fileSize', render: formatSize },
          { title: '强制', dataIndex: 'mandatory', render: (mandatory: boolean) => mandatory ? <Tag color="red">强制</Tag> : <Tag>普通</Tag> },
          { title: '状态', dataIndex: 'published', render: (published: boolean) => published ? <Tag color="green">已发布</Tag> : <Tag color="default">草稿</Tag> },
          {
            title: '操作',
            render: (_, record) => (
              <Space size={4}>
                <Upload
                  showUploadList={false}
                  customRequest={(options) => uploadPackage(record, options)}
                  accept={record.platform === 'MAC' ? '.dmg,.pkg' : '.exe,.msi'}
                  disabled={uploadingVersionId === record.id}
                >
                  <Tooltip title="上传安装包">
                    <Button
                      className="table-action"
                      size="small"
                      type="text"
                      loading={uploadingVersionId === record.id}
                      icon={<CloudUploadOutlined />}
                    />
                  </Tooltip>
                </Upload>
                {record.downloadUrl ? (
                  <Tooltip title="下载安装包">
                    <Button className="table-action" size="small" type="text" icon={<DownloadOutlined />} href={record.downloadUrl} target="_blank" />
                  </Tooltip>
                ) : null}
                <Tooltip title={record.published ? '下架' : '发布'}>
                  <Button
                    className="table-action"
                    size="small"
                    type="text"
                    icon={record.published ? <StopOutlined /> : <RocketOutlined />}
                    onClick={() => setPublished(record, !record.published)}
                  />
                </Tooltip>
              </Space>
            ),
          },
        ]}
      />
      {uploadingVersionId ? (
        <Modal title="安装包上传中" open footer={null} closable={false}>
          <Progress percent={uploadProgress} status="active" />
        </Modal>
      ) : null}
      <Modal title="创建桌面版本" open={open} onCancel={() => setOpen(false)} onOk={() => form.submit()} destroyOnClose>
        <Form form={form} layout="vertical" onFinish={submit}>
          <Form.Item name="platform" label="平台" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'MAC', label: 'macOS' },
                { value: 'WINDOWS', label: 'Windows' },
              ]}
            />
          </Form.Item>
          <Form.Item name="version" label="版本号" rules={[{ required: true }]}>
            <Input placeholder="0.2.0" />
          </Form.Item>
          <Form.Item name="releaseNotes" label="更新说明">
            <Input.TextArea rows={5} placeholder="本次更新内容" />
          </Form.Item>
          <Form.Item name="mandatory" label="强制更新" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </DataPage>
  );
}
