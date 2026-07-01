import {
  CloudUploadOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  EyeOutlined,
  FileWordOutlined,
  PlusOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import { Button, Form, Input, InputNumber, Modal, Popconfirm, Progress, Select, Space, Table, Tag, Tooltip, Upload } from 'antd';
import type { UploadFile } from 'antd';
import { renderAsync } from 'docx-preview';
import type { UploadRequestOption } from 'rc-upload/lib/interface';
import { useEffect, useMemo, useRef, useState } from 'react';
import { DataPage } from '../../components/DataPage';
import { TableToolbar } from '../../components/TableToolbar';
import { appMessage } from '../../shared/appMessage';
import { formatDateTime } from '../../shared/format';
import { apiDelete, apiGet, http } from '../../shared/http';
import type { ContractTemplate } from '../../shared/types';
import { useAsyncData } from '../../shared/useAsyncData';

type TemplateForm = {
  platform: ContractTemplate['platform'];
  type: ContractTemplate['type'];
  name: string;
  weight?: number;
  file?: UploadFile[];
};

type WeightForm = {
  weight: number;
};

const platformOptions: { value: ContractTemplate['platform']; label: string }[] = [
  { value: 'WECHAT_VIDEO', label: '视频号' },
  { value: 'TIKTOK', label: 'TK' },
  { value: 'DOUYIN', label: '抖音' },
];

const contractTypeOptions: { value: ContractTemplate['type']; label: string }[] = [
  { value: 'COST_CONTRACT', label: '成本合同' },
  { value: 'PURCHASE_CONTRACT', label: '购买合同' },
  { value: 'RIGHTS_STATEMENT', label: '权利声明' },
];

const platformAllowedContractTypes: Record<ContractTemplate['platform'], ContractTemplate['type'][]> = {
  WECHAT_VIDEO: ['COST_CONTRACT', 'PURCHASE_CONTRACT', 'RIGHTS_STATEMENT'],
  TIKTOK: ['PURCHASE_CONTRACT'],
  DOUYIN: ['PURCHASE_CONTRACT'],
};

function formatSize(size: number) {
  if (!size) return '-';
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function uploadFileFromEvent(event: { fileList?: UploadFile[] } | UploadFile[]) {
  return Array.isArray(event) ? event : event?.fileList;
}

function contractOptionsFor(platform: ContractTemplate['platform']) {
  const allowed = platformAllowedContractTypes[platform] ?? ['PURCHASE_CONTRACT'];
  return contractTypeOptions.filter((option) => allowed.includes(option.value));
}

function resolveResourceUrl(url: string) {
  return new URL(url, window.location.origin).toString();
}

function ContractPreviewModal({
  template,
  onClose,
}: {
  template: ContractTemplate | null;
  onClose: () => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!template?.downloadUrl || !containerRef.current) return;
    const controller = new AbortController();
    const container = containerRef.current;
    container.innerHTML = '';
    setLoading(true);
    fetch(resolveResourceUrl(template.downloadUrl), { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.blob();
      })
      .then((blob) => renderAsync(blob, container, undefined, {
        className: 'docx-preview-document',
        inWrapper: false,
        ignoreFonts: true,
      }))
      .catch((error) => {
        if (!controller.signal.aborted) {
          container.innerHTML = '<div class="contract-preview-error">Word 预览加载失败，请下载后查看。</div>';
          appMessage.error(error instanceof Error ? error.message : 'Word 预览加载失败');
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [template]);

  return (
    <Modal
      title={template ? `${template.platformLabel} · ${template.label} · ${template.name}` : 'Word 预览'}
      open={Boolean(template)}
      onCancel={onClose}
      footer={null}
      width={980}
      destroyOnClose
    >
      <div className="contract-preview-shell">
        {loading ? <Progress percent={70} status="active" showInfo={false} /> : null}
        <div ref={containerRef} className="contract-preview-doc" />
      </div>
    </Modal>
  );
}

export function ContractTemplatesPage() {
  const [reload, setReload] = useState(0);
  const [filters, setFilters] = useState<Record<string, unknown>>({});
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [uploadingId, setUploadingId] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [previewTemplate, setPreviewTemplate] = useState<ContractTemplate | null>(null);
  const [weightTemplate, setWeightTemplate] = useState<ContractTemplate | null>(null);
  const [form] = Form.useForm<TemplateForm>();
  const [weightForm] = Form.useForm<WeightForm>();
  const selectedPlatform = Form.useWatch('platform', form) ?? 'WECHAT_VIDEO';
  const { data, loading } = useAsyncData(
    () => apiGet<ContractTemplate[]>('/admin/contract-templates'),
    [reload],
  );
  const filteredData = useMemo(() => {
    return (data ?? []).filter((template) => {
      const platform = filters.platform;
      const type = filters.type;
      return (!platform || template.platform === platform) && (!type || template.type === type);
    });
  }, [data, filters]);

  function showCreate() {
    form.setFieldsValue({ platform: 'WECHAT_VIDEO', type: 'COST_CONTRACT', name: '', weight: 0, file: [] });
    setOpen(true);
  }

  function showWeightEdit(record: ContractTemplate) {
    setWeightTemplate(record);
    weightForm.setFieldsValue({ weight: record.weight ?? 0 });
  }

  async function submit(values: TemplateForm) {
    const file = values.file?.[0]?.originFileObj;
    if (!file) {
      appMessage.error('请选择 Word 模板文件');
      return;
    }
    const formData = new FormData();
    formData.append('platform', values.platform);
    formData.append('type', values.type);
    formData.append('weight', String(values.weight ?? 0));
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

  async function submitWeight(values: WeightForm) {
    if (!weightTemplate) return;
    await http.patch(`/admin/contract-templates/${weightTemplate.id}/weight`, {
      weight: values.weight ?? 0,
    });
    appMessage.success('权重已更新');
    setWeightTemplate(null);
    setReload((value) => value + 1);
  }

  return (
    <DataPage
      title="合同模版"
      extra={(
        <TableToolbar
          fields={[
            {
              name: 'platform',
              placeholder: '媒体号类型',
              type: 'select',
              options: platformOptions,
              width: 160,
            },
            {
              name: 'type',
              placeholder: '合同类型',
              type: 'select',
              options: contractTypeOptions,
              width: 160,
            },
          ]}
          onSearch={setFilters}
        />
      )}
      actions={<Button type="primary" icon={<PlusOutlined />} onClick={showCreate}>新增模板</Button>}
    >
      <Table<ContractTemplate>
        rowKey="id"
        loading={loading}
        dataSource={filteredData}
        pagination={{ pageSize: 10, showSizeChanger: false, showTotal: (total) => `共 ${total} 条` }}
        columns={[
          {
            title: '媒体号类型',
            dataIndex: 'platformLabel',
            width: 130,
            filters: platformOptions.map((option) => ({ text: option.label, value: option.value })),
            onFilter: (value, record) => record.platform === value,
            render: (label: string) => <Tag color="geekblue">{label}</Tag>,
          },
          {
            title: '合同类型',
            dataIndex: 'label',
            width: 140,
            filters: contractTypeOptions.map((option) => ({ text: option.label, value: option.value })),
            onFilter: (value, record) => record.type === value,
            render: (label: string) => <Tag color="blue">{label}</Tag>,
          },
          {
            title: '权重',
            dataIndex: 'weight',
            width: 90,
            defaultSortOrder: 'descend',
            sortDirections: ['descend', 'ascend'],
            sorter: (a, b) => a.weight - b.weight,
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
                <Tooltip title="预览 Word 模板">
                  <Button
                    className="table-action"
                    size="small"
                    type="text"
                    disabled={!record.downloadUrl}
                    icon={<EyeOutlined />}
                    onClick={() => setPreviewTemplate(record)}
                  />
                </Tooltip>
                <Tooltip title="设置权重">
                  <Button
                    className="table-action"
                    size="small"
                    type="text"
                    icon={<EditOutlined />}
                    onClick={() => showWeightEdit(record)}
                  />
                </Tooltip>
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
          <Form.Item name="platform" label="媒体号类型" rules={[{ required: true }]}>
            <Select
              options={platformOptions}
              onChange={(platform: ContractTemplate['platform']) => {
                const nextOptions = contractOptionsFor(platform);
                form.setFieldValue('type', nextOptions[0]?.value);
              }}
            />
          </Form.Item>
          <Form.Item name="type" label="合同类型" rules={[{ required: true }]}>
            <Select options={contractOptionsFor(selectedPlatform)} />
          </Form.Item>
          <Form.Item name="name" label="模板名称" rules={[{ required: true, message: '请输入模板名称' }]}>
            <Input placeholder="例如：成本合同-标准版" />
          </Form.Item>
          <Form.Item name="weight" label="权重" tooltip="权重越大，客户端下载系统模版时越靠前">
            <InputNumber min={0} max={999999} precision={0} style={{ width: '100%' }} />
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
      <Modal
        title={weightTemplate ? `设置权重：${weightTemplate.name}` : '设置权重'}
        open={Boolean(weightTemplate)}
        onCancel={() => setWeightTemplate(null)}
        onOk={() => weightForm.submit()}
        destroyOnClose
      >
        <Form form={weightForm} layout="vertical" onFinish={submitWeight}>
          <Form.Item
            name="weight"
            label="权重"
            tooltip="权重越大，客户端下载系统模版时越靠前；同权重按上传时间倒序"
            rules={[{ required: true, message: '请输入权重' }]}
          >
            <InputNumber min={0} max={999999} precision={0} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
      <ContractPreviewModal template={previewTemplate} onClose={() => setPreviewTemplate(null)} />
    </DataPage>
  );
}
