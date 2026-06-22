import {
  CloudUploadOutlined,
  DeleteOutlined,
  DownloadOutlined,
  FileWordOutlined,
  PlusOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import { Button, Form, Input, Modal, Popconfirm, Progress, Select, Space, Table, Tag, Tooltip, Upload } from 'antd';
import type { UploadFile } from 'antd';
import type { UploadRequestOption } from 'rc-upload/lib/interface';
import { useState } from 'react';
import { DataPage } from '../../components/DataPage';
import { appMessage } from '../../shared/appMessage';
import { formatDateTime } from '../../shared/format';
import { apiDelete, apiGet, http } from '../../shared/http';
import type { ContractTemplate } from '../../shared/types';
import { useAsyncData } from '../../shared/useAsyncData';

type TemplateForm = {
  type: ContractTemplate['type'];
  name: string;
  file?: UploadFile[];
};

const contractTypeOptions = [
  { value: 'COST_CONTRACT', label: '成本合同' },
  { value: 'PURCHASE_CONTRACT', label: '买剧合同' },
];

function formatSize(size: number) {
  if (!size) return '-';
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function uploadFileFromEvent(event: { fileList?: UploadFile[] } | UploadFile[]) {
  return Array.isArray(event) ? event : event?.fileList;
}

export function ContractTemplatesPage() {
  const [reload, setReload] = useState(0);
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [uploadingId, setUploadingId] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [form] = Form.useForm<TemplateForm>();
  const { data, loading } = useAsyncData(
    () => apiGet<ContractTemplate[]>('/admin/contract-templates'),
    [reload],
  );

  function showCreate() {
    form.setFieldsValue({ type: 'COST_CONTRACT', name: '', file: [] });
    setOpen(true);
  }

  async function submit(values: TemplateForm) {
    const file = values.file?.[0]?.originFileObj;
    if (!file) {
      appMessage.error('请选择 Word 模板文件');
      return;
    }
    const formData = new FormData();
    formData.append('type', values.type);
    formData.append('name', values.name);
    formData.append('file', file);
    setCreating(true);
    setUploadProgress(0);
    try {
      await http.post('/admin/contract-templates', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 5 * 60 * 1000,
        onUploadProgress: (event) => {
          if (event.total) setUploadProgress(Math.round((event.loaded / event.total) * 100));
        },
      });
      appMessage.success('合同模板已新增');
      setOpen(false);
      form.resetFields();
      setReload((value) => value + 1);
    } finally {
      setCreating(false);
      setUploadProgress(0);
    }
  }

  async function replaceTemplate(record: ContractTemplate, options: UploadRequestOption) {
    const formData = new FormData();
    formData.append('file', options.file as File);
    setUploadingId(record.id);
    setUploadProgress(0);
    try {
      await http.post(`/admin/contract-templates/${record.id}/file`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 5 * 60 * 1000,
        onUploadProgress: (event) => {
          if (event.total) {
            const percent = Math.round((event.loaded / event.total) * 100);
            setUploadProgress(percent);
            options.onProgress?.({ percent });
          }
        },
      });
      options.onSuccess?.({}, new XMLHttpRequest());
      appMessage.success('合同模板已替换');
      setReload((value) => value + 1);
    } catch (error) {
      options.onError?.(error as Error);
    } finally {
      setUploadingId(null);
      setUploadProgress(0);
    }
  }

  async function deleteTemplate(record: ContractTemplate) {
    await apiDelete(`/admin/contract-templates/${record.id}`);
    appMessage.success('合同模板已删除');
    setReload((value) => value + 1);
  }

  return (
    <DataPage
      title="合同模版"
      actions={<Button type="primary" icon={<PlusOutlined />} onClick={showCreate}>新增模板</Button>}
    >
      <Table<ContractTemplate>
        rowKey="id"
        loading={loading}
        dataSource={data ?? []}
        pagination={{ pageSize: 10, showSizeChanger: false, showTotal: (total) => `共 ${total} 条` }}
        columns={[
          {
            title: '合同类型',
            dataIndex: 'label',
            width: 140,
            render: (label: string) => <Tag color="blue">{label}</Tag>,
          },
          {
            title: '模板名称',
            dataIndex: 'name',
            render: (name: string) => (
              <Space>
                <FileWordOutlined />
                <span>{name}</span>
              </Space>
            ),
          },
          {
            title: '当前文件',
            dataIndex: 'fileName',
            render: (_, record) => record.downloadUrl ? (
              <a href={record.downloadUrl} target="_blank" rel="noreferrer">{record.fileName}</a>
            ) : '-',
          },
          { title: '大小', dataIndex: 'fileSize', width: 120, render: formatSize },
          { title: '上传时间', dataIndex: 'uploadedAt', width: 190, render: formatDateTime },
          {
            title: '操作',
            width: 150,
            render: (_, record) => (
              <Space size={4}>
                <Upload
                  showUploadList={false}
                  customRequest={(options) => replaceTemplate(record, options)}
                  accept=".docx"
                  disabled={uploadingId === record.id}
                >
                  <Tooltip title="替换模板文件">
                    <Button
                      className="table-action"
                      size="small"
                      type="text"
                      loading={uploadingId === record.id}
                      icon={<CloudUploadOutlined />}
                    />
                  </Tooltip>
                </Upload>
                <Tooltip title="下载模板">
                  <Button className="table-action" size="small" type="text" icon={<DownloadOutlined />} href={record.downloadUrl} target="_blank" />
                </Tooltip>
                <Tooltip title="删除模板">
                  <Popconfirm title="删除这个合同模板？" onConfirm={() => deleteTemplate(record)}>
                    <Button
                      className="table-action"
                      size="small"
                      type="text"
                      danger
                      icon={<DeleteOutlined />}
                    />
                  </Popconfirm>
                </Tooltip>
              </Space>
            ),
          },
        ]}
      />
      <Modal title="新增合同模板" open={open} onCancel={() => setOpen(false)} onOk={() => form.submit()} confirmLoading={creating} destroyOnClose>
        <Form form={form} layout="vertical" onFinish={submit}>
          <Form.Item name="type" label="合同类型" rules={[{ required: true }]}>
            <Select options={contractTypeOptions} />
          </Form.Item>
          <Form.Item name="name" label="模板名称" rules={[{ required: true, message: '请输入模板名称' }]}>
            <Input placeholder="例如：成本合同-标准版" />
          </Form.Item>
          <Form.Item
            name="file"
            label="Word 模板"
            valuePropName="fileList"
            getValueFromEvent={uploadFileFromEvent}
            rules={[{ required: true, message: '请选择 Word 模板文件' }]}
          >
            <Upload beforeUpload={() => false} maxCount={1} accept=".docx">
              <Button icon={<UploadOutlined />}>选择 .docx 文件</Button>
            </Upload>
          </Form.Item>
        </Form>
        {creating ? <Progress percent={uploadProgress} status="active" /> : null}
      </Modal>
      {uploadingId ? (
        <Modal title="合同模板替换中" open footer={null} closable={false}>
          <Progress percent={uploadProgress} status="active" />
        </Modal>
      ) : null}
    </DataPage>
  );
}
