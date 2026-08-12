import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons';
import { Alert, Button, Form, Input, Modal, Switch, Tag, Tooltip, Typography } from 'antd';
import { useState } from 'react';
import { AdminTable } from '../../components/AdminTable';
import { DataPage } from '../../components/DataPage';
import { TableToolbar } from '../../components/TableToolbar';
import { appMessage } from '../../shared/appMessage';
import { apiDelete, apiGetPage, apiPut } from '../../shared/http';
import type { SystemConfig } from '../../shared/types';

type ConfigHelp = {
  description: string;
  values?: string;
};

const CONFIG_HELP: Record<string, ConfigHelp> = {
  'openai.provider': {
    description: 'OpenAI 服务开关。official 使用官方 OpenAI 配置；thirdParty 使用第三方 OpenAI-compatible 配置。',
    values: '可选值：official、thirdParty。兼容别名：tokenfree、proxy、custom、third-party、third_party。',
  },
  'openai.baseUrl': {
    description: '官方 OpenAI API 地址，仅 openai.provider=official 时使用。',
    values: '默认值：https://api.openai.com/v1',
  },
  'openai.apiKey': {
    description: '官方 OpenAI API Key，仅 openai.provider=official 时使用。',
  },
  'openai.textModel': {
    description: '官方文本模型，仅 openai.provider=official 时使用。',
  },
  'openai.imageModel': {
    description: '官方图片模型，仅 openai.provider=official 时使用。',
  },
  'openai.thirdParty.baseUrl': {
    description: '第三方 OpenAI-compatible API 地址，仅 openai.provider=thirdParty 时使用。',
    values: 'tokenfree 当前值：https://tokenfree.biz/v1',
  },
  'openai.thirdParty.apiKey': {
    description: '第三方 OpenAI-compatible API Key，仅 openai.provider=thirdParty 时使用。',
  },
  'openai.thirdParty.textModel': {
    description: '第三方文本模型，仅 openai.provider=thirdParty 时使用。',
  },
  'openai.thirdParty.imageModel': {
    description: '第三方图片模型，仅 openai.provider=thirdParty 时使用。',
  },
  'openai.thirdParty.extraHeaders': {
    description: '第三方接口需要附加的请求头，支持每行一个 Header，格式为 Header-Name: value。',
    values: 'tokenfree 当前值：x-openai-actor-authorization: local-image-extension',
  },
  'openai.thirdParty.disableResponseStorage': {
    description: '第三方文本请求是否追加 store=false，避免代理侧持久化响应。',
    values: '可选值：true、false。建议保持 true。',
  },
};

function configHelp(key?: string) {
  if (!key) {
    return undefined;
  }
  return CONFIG_HELP[key.trim()];
}

function ConfigHelpText({ configKey }: { configKey: string }) {
  const help = configHelp(configKey);
  if (!help) {
    return <Typography.Text type="secondary">-</Typography.Text>;
  }
  return (
    <Tooltip title={help.values ? `${help.description}\n${help.values}` : help.description}>
      <Typography.Text type="secondary" ellipsis style={{ maxWidth: 440 }}>
        {help.description}
      </Typography.Text>
    </Tooltip>
  );
}

export function ConfigsPage() {
  const [version, setVersion] = useState(0);
  const [filters, setFilters] = useState<Record<string, unknown>>({});
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const editingKey = Form.useWatch('key', form);
  const editingHelp = configHelp(editingKey);

  function showEditor(config?: SystemConfig) {
    form.setFieldsValue(config ?? { secret: false });
    setOpen(true);
  }

  async function submit(values: SystemConfig) {
    await apiPut(`/admin/configs/${encodeURIComponent(values.key)}`, {
      value: values.value,
      secret: values.secret,
    });
    appMessage.success('配置已保存');
    setOpen(false);
    setVersion((value) => value + 1);
  }

  function remove(config: SystemConfig) {
    Modal.confirm({
      title: '删除系统配置',
      content: `确认删除配置项 ${config.key} 吗？`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        await apiDelete(`/admin/configs/${encodeURIComponent(config.key)}`);
        appMessage.success('配置已删除');
        setVersion((value) => value + 1);
      },
    });
  }

  return (
    <DataPage
      title="系统配置"
      actions={<Button type="primary" icon={<PlusOutlined />} onClick={() => showEditor()}>写入配置</Button>}
      extra={(
        <TableToolbar
          fields={[
            { name: 'keyword', placeholder: '搜索配置项/值' },
            {
              name: 'secret',
              placeholder: '敏感类型',
              type: 'select',
              options: [
                { value: true, label: '脱敏' },
                { value: false, label: '普通' },
              ],
            },
          ]}
          onSearch={setFilters}
        />
      )}
    >
      <AdminTable<SystemConfig>
        rowKey="key"
        reloadKey={`${version}-${JSON.stringify(filters)}`}
        loadPage={(page, size) => apiGetPage<SystemConfig>('/admin/configs', page, size, filters as Record<string, string | number | boolean | string[] | undefined>)}
        columns={[
          { title: '配置项', dataIndex: 'key' },
          { title: '值', dataIndex: 'value' },
          { title: '说明', dataIndex: 'key', render: (key: string) => <ConfigHelpText configKey={key} /> },
          { title: '敏感', dataIndex: 'secret', render: (secret: boolean) => secret ? <Tag color="orange">脱敏</Tag> : <Tag>普通</Tag> },
          {
            title: '操作',
            render: (_, record) => (
              <>
                <Tooltip title="更新">
                  <Button className="table-action" size="small" type="text" icon={<EditOutlined />} onClick={() => showEditor(record)} />
                </Tooltip>
                <Tooltip title="删除">
                  <Button
                    className="table-action"
                    size="small"
                    type="text"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={() => remove(record)}
                  />
                </Tooltip>
              </>
            ),
          },
        ]}
      />
      <Modal title="写入系统配置" open={open} onCancel={() => setOpen(false)} onOk={() => form.submit()} destroyOnClose>
        <Form form={form} layout="vertical" onFinish={submit}>
          <Form.Item name="key" label="配置项" rules={[{ required: true }]}>
            <Input placeholder="baidu.scanRoot" />
          </Form.Item>
          {editingHelp ? (
            <Alert
              showIcon
              type="info"
              message={editingHelp.description}
              description={editingHelp.values}
              style={{ marginBottom: 16 }}
            />
          ) : null}
          <Form.Item name="value" label="配置值" rules={[{ required: true }]}>
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item name="secret" label="敏感配置" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </DataPage>
  );
}
