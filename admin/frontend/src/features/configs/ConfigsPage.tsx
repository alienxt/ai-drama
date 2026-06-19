import { EditOutlined, PlusOutlined } from '@ant-design/icons';
import { Button, Form, Input, Modal, Switch, Tag, Tooltip } from 'antd';
import { useState } from 'react';
import { AdminTable } from '../../components/AdminTable';
import { DataPage } from '../../components/DataPage';
import { TableToolbar } from '../../components/TableToolbar';
import { appMessage } from '../../shared/appMessage';
import { apiGetPage, apiPut } from '../../shared/http';
import type { SystemConfig } from '../../shared/types';

export function ConfigsPage() {
  const [version, setVersion] = useState(0);
  const [filters, setFilters] = useState<Record<string, unknown>>({});
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

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
          { title: '敏感', dataIndex: 'secret', render: (secret: boolean) => secret ? <Tag color="orange">脱敏</Tag> : <Tag>普通</Tag> },
          {
            title: '操作',
            render: (_, record) => (
              <Tooltip title="更新">
                <Button className="table-action" size="small" type="text" icon={<EditOutlined />} onClick={() => showEditor(record)} />
              </Tooltip>
            ),
          },
        ]}
      />
      <Modal title="写入系统配置" open={open} onCancel={() => setOpen(false)} onOk={() => form.submit()} destroyOnClose>
        <Form form={form} layout="vertical" onFinish={submit}>
          <Form.Item name="key" label="配置项" rules={[{ required: true }]}>
            <Input placeholder="baidu.scanRoot" />
          </Form.Item>
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
