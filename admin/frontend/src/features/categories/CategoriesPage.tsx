import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons';
import { Button, Form, Input, InputNumber, Modal, Popconfirm, Space, Switch, Tag, Tooltip } from 'antd';
import { useState } from 'react';
import { AdminTable } from '../../components/AdminTable';
import { DataPage } from '../../components/DataPage';
import { TableToolbar } from '../../components/TableToolbar';
import { appMessage } from '../../shared/appMessage';
import { apiDelete, apiGetPage, apiPost, apiPut } from '../../shared/http';
import type { DramaCategory } from '../../shared/types';

export function CategoriesPage() {
  const [version, setVersion] = useState(0);
  const [filters, setFilters] = useState<Record<string, unknown>>({});
  const [editing, setEditing] = useState<DramaCategory | null>(null);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  function showEditor(category?: DramaCategory) {
    setEditing(category ?? null);
    form.setFieldsValue(category ?? { enabled: true, sortOrder: 100 });
    setOpen(true);
  }

  async function submit(values: DramaCategory) {
    if (editing) {
      await apiPut(`/admin/categories/${editing.id}`, values);
      appMessage.success('类别已更新');
    } else {
      await apiPost('/admin/categories', values);
      appMessage.success('类别已创建');
    }
    setOpen(false);
    setVersion((value) => value + 1);
  }

  async function remove(category: DramaCategory) {
    await apiDelete(`/admin/categories/${category.id}`);
    appMessage.success('类别已删除');
    setVersion((value) => value + 1);
  }

  return (
    <DataPage
      title="短剧类别"
      actions={<Button type="primary" icon={<PlusOutlined />} onClick={() => showEditor()}>新增类别</Button>}
      extra={(
        <TableToolbar
          fields={[
            { name: 'keyword', placeholder: '搜索名称/编码' },
            {
              name: 'enabled',
              placeholder: '状态',
              type: 'select',
              options: [
                { value: true, label: '启用' },
                { value: false, label: '禁用' },
              ],
            },
          ]}
          onSearch={setFilters}
        />
      )}
    >
      <AdminTable<DramaCategory>
        rowKey="id"
        reloadKey={`${version}-${JSON.stringify(filters)}`}
        loadPage={(page, size) => apiGetPage<DramaCategory>('/admin/categories', page, size, filters as Record<string, string | number | boolean | string[] | undefined>)}
        columns={[
          { title: '名称', dataIndex: 'name' },
          { title: '编码', dataIndex: 'code' },
          { title: '排序', dataIndex: 'sortOrder', width: 100 },
          { title: '状态', dataIndex: 'enabled', render: (enabled: boolean) => <Tag color={enabled ? 'green' : 'default'}>{enabled ? '启用' : '禁用'}</Tag> },
          {
            title: '操作',
            render: (_, record) => (
              <Space size={4}>
                <Tooltip title="编辑">
                  <Button className="table-action" size="small" type="text" icon={<EditOutlined />} onClick={() => showEditor(record)} />
                </Tooltip>
                <Popconfirm title="删除这个类别？" onConfirm={() => remove(record)}>
                  <Tooltip title="删除">
                    <Button className="table-action" size="small" type="text" danger icon={<DeleteOutlined />} />
                  </Tooltip>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />
      <Modal title={editing ? '编辑类别' : '新增类别'} open={open} onCancel={() => setOpen(false)} onOk={() => form.submit()} destroyOnClose>
        <Form form={form} layout="vertical" onFinish={submit}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="code" label="编码" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="sortOrder" label="排序" rules={[{ required: true }]}>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </DataPage>
  );
}
