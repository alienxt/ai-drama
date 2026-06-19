import { Button, Form, Input, InputNumber, Select, Space } from 'antd';
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons';

export type FilterField = {
  name: string;
  placeholder: string;
  type?: 'search' | 'select' | 'number';
  options?: { value: string | boolean; label: string }[];
  allowClear?: boolean;
  mode?: 'multiple';
  width?: number;
};

type TableToolbarProps = {
  fields: FilterField[];
  initialValues?: Record<string, unknown>;
  onSearch: (values: Record<string, unknown>) => void;
};

export function TableToolbar({ fields, initialValues, onSearch }: TableToolbarProps) {
  const [form] = Form.useForm();

  function reset() {
    form.resetFields();
    onSearch(initialValues ?? {});
  }

  return (
    <Form className="table-toolbar" form={form} initialValues={initialValues} onFinish={onSearch}>
      <Space size={8} wrap>
        {fields.map((field) => (
          <Form.Item key={field.name} name={field.name} className="toolbar-field">
            {field.type === 'select' ? (
              <Select
                allowClear={field.allowClear ?? true}
                mode={field.mode}
                options={field.options}
                placeholder={field.placeholder}
                style={{ width: field.width ?? 150 }}
              />
            ) : field.type === 'number' ? (
              <InputNumber
                min={1}
                precision={0}
                placeholder={field.placeholder}
                style={{ width: field.width ?? 120 }}
              />
            ) : (
              <Input
                allowClear
                prefix={<SearchOutlined />}
                placeholder={field.placeholder}
                style={{ width: field.width ?? 220 }}
              />
            )}
          </Form.Item>
        ))}
        <Button type="primary" htmlType="submit" icon={<SearchOutlined />}>搜索</Button>
        <Button icon={<ReloadOutlined />} onClick={reset}>重置</Button>
      </Space>
    </Form>
  );
}
