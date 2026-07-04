import { ApiOutlined, CheckCircleOutlined, DisconnectOutlined, KeyOutlined, PlusOutlined, StopOutlined } from '@ant-design/icons';
import { Button, Form, Input, Modal, Popconfirm, Select, Space, Tag, Tooltip } from 'antd';
import { useState } from 'react';
import { AdminTable } from '../../components/AdminTable';
import { DataPage } from '../../components/DataPage';
import { TableToolbar } from '../../components/TableToolbar';
import { appMessage } from '../../shared/appMessage';
import { apiDelete, apiGetPage, apiPatch, apiPost } from '../../shared/http';
import { accountRoleLabel } from '../../shared/labels';
import type { Account } from '../../shared/types';

type AccountManagementPageProps = {
  title: string;
  createLabel: string;
  modalTitle: string;
  defaultRoles: string[];
  roleOptions: { value: string; label: string }[];
  roles: string[];
  successMessage: string;
};

function AccountManagementPage({
  title,
  createLabel,
  modalTitle,
  defaultRoles,
  roleOptions,
  roles,
  successMessage,
}: AccountManagementPageProps) {
  const [version, setVersion] = useState(0);
  const [filters, setFilters] = useState<Record<string, unknown>>({ roles });
  const [open, setOpen] = useState(false);
  const [bindingAccount, setBindingAccount] = useState<Account | null>(null);
  const [passwordAccount, setPasswordAccount] = useState<Account | null>(null);
  const [form] = Form.useForm();
  const [deviceForm] = Form.useForm<{ deviceId: string }>();
  const [passwordForm] = Form.useForm<{ password: string; confirmPassword: string }>();
  const isDesktopUserPage = roles.includes('DESKTOP_USER');

  async function create(values: { username: string; password: string; roles: string[] }) {
    await apiPost('/admin/accounts', values);
    appMessage.success(successMessage);
    setOpen(false);
    form.resetFields();
    setVersion((value) => value + 1);
  }

  async function setEnabled(account: Account, enabled: boolean) {
    await apiPatch(`/admin/accounts/${account.id}/enabled`, { enabled });
    appMessage.success(enabled ? '账号已启用' : '账号已禁用');
    setVersion((value) => value + 1);
  }

  function showDeviceBinding(account: Account) {
    setBindingAccount(account);
    deviceForm.setFieldsValue({ deviceId: account.boundDeviceId ?? '' });
  }

  async function bindDevice(values: { deviceId: string }) {
    if (!bindingAccount) return;
    await apiPatch(`/admin/accounts/${bindingAccount.id}/device-binding`, { deviceId: values.deviceId });
    appMessage.success('绑定设备已更新');
    setBindingAccount(null);
    deviceForm.resetFields();
    setVersion((value) => value + 1);
  }

  async function clearDeviceBinding(account: Account) {
    await apiDelete(`/admin/accounts/${account.id}/device-binding`);
    appMessage.success('绑定设备已解绑');
    setVersion((value) => value + 1);
  }

  function showPasswordReset(account: Account) {
    setPasswordAccount(account);
    passwordForm.resetFields();
  }

  async function resetPassword(values: { password: string }) {
    if (!passwordAccount) return;
    await apiPatch(`/admin/accounts/${passwordAccount.id}/password`, { password: values.password });
    appMessage.success('密码已更新');
    setPasswordAccount(null);
    passwordForm.resetFields();
  }

  function renderDevice(value?: string) {
    return value ? <Tag className="device-tag">{value}</Tag> : <span className="muted">未绑定</span>;
  }

  return (
    <DataPage
      title={title}
      actions={<Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>{createLabel}</Button>}
      extra={(
        <TableToolbar
          initialValues={{ roles }}
          fields={[
            { name: 'keyword', placeholder: '搜索用户名' },
            {
              name: 'enabled',
              placeholder: '状态',
              type: 'select',
              options: [
                { value: true, label: '启用' },
                { value: false, label: '禁用' },
              ],
            },
            {
              name: 'roles',
              placeholder: '角色',
              type: 'select',
              mode: 'multiple',
              options: roleOptions,
              width: 190,
            },
          ]}
          onSearch={(values) => setFilters({ ...values, roles: (values.roles as string[] | undefined) ?? roles })}
        />
      )}
    >
      <AdminTable<Account>
        rowKey="id"
        reloadKey={`${version}-${JSON.stringify(filters)}`}
        loadPage={(page, size) => apiGetPage<Account>('/admin/accounts', page, size, filters as Record<string, string | number | boolean | string[] | undefined>)}
        columns={[
          { title: '用户名', dataIndex: 'username' },
          {
            title: '角色',
            dataIndex: 'roles',
            render: (roles: string[]) => roles.map((role) => <Tag key={role}>{accountRoleLabel(role)}</Tag>),
          },
          { title: '状态', dataIndex: 'enabled', render: (enabled: boolean) => <Tag color={enabled ? 'green' : 'red'}>{enabled ? '启用' : '禁用'}</Tag> },
          { title: '绑定设备', dataIndex: 'boundDeviceId', render: renderDevice },
          { title: '最后登录设备', dataIndex: 'lastLoginDeviceId', render: renderDevice },
          { title: '最后登录', dataIndex: 'lastLoginAt', render: (value?: string) => value || '-' },
          {
            title: '操作',
            render: (_, record) => (
              <Space size={4}>
                {isDesktopUserPage ? (
                  <>
                    <Tooltip title="绑定设备">
                      <Button
                        className="table-action"
                        size="small"
                        type="text"
                        icon={<ApiOutlined />}
                        onClick={() => showDeviceBinding(record)}
                      />
                    </Tooltip>
                    <Popconfirm title="解绑这个设备？" onConfirm={() => clearDeviceBinding(record)} disabled={!record.boundDeviceId}>
                      <Tooltip title="解绑设备">
                        <Button
                          className="table-action"
                          size="small"
                          type="text"
                          danger
                          disabled={!record.boundDeviceId}
                          icon={<DisconnectOutlined />}
                        />
                      </Tooltip>
                    </Popconfirm>
                  </>
                ) : null}
                <Tooltip title="修改密码">
                  <Button
                    className="table-action"
                    size="small"
                    type="text"
                    icon={<KeyOutlined />}
                    onClick={() => showPasswordReset(record)}
                  />
                </Tooltip>
                <Tooltip title="禁用">
                  <Button
                    className="table-action"
                    size="small"
                    type="text"
                    danger
                    disabled={!record.enabled}
                    icon={<StopOutlined />}
                    onClick={() => setEnabled(record, false)}
                  />
                </Tooltip>
                <Tooltip title="启用">
                  <Button
                    className="table-action"
                    size="small"
                    type="text"
                    disabled={record.enabled}
                    icon={<CheckCircleOutlined />}
                    onClick={() => setEnabled(record, true)}
                  />
                </Tooltip>
              </Space>
            ),
          },
        ]}
      />
      <Modal title={modalTitle} open={open} onCancel={() => setOpen(false)} onOk={() => form.submit()} destroyOnClose>
        <Form form={form} layout="vertical" onFinish={create} initialValues={{ roles: defaultRoles }}>
          <Form.Item name="username" label="用户名" rules={[{ required: true }]}>
            <Input autoComplete="off" />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, min: 8 }]}>
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item name="roles" label="角色" rules={[{ required: true }]}>
            <Select mode="multiple" options={roleOptions} />
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title={`修改密码：${passwordAccount?.username ?? ''}`}
        open={!!passwordAccount}
        onCancel={() => setPasswordAccount(null)}
        onOk={() => passwordForm.submit()}
        destroyOnClose
      >
        <Form form={passwordForm} layout="vertical" onFinish={resetPassword}>
          <Form.Item
            name="password"
            label="新密码"
            rules={[
              { required: true, message: '请输入新密码' },
              { min: 8, message: '密码至少 8 位' },
            ]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item
            name="confirmPassword"
            label="确认新密码"
            dependencies={['password']}
            rules={[
              { required: true, message: '请再次输入新密码' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('password') === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error('两次输入的密码不一致'));
                },
              }),
            ]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title={`绑定设备：${bindingAccount?.username ?? ''}`}
        open={!!bindingAccount}
        onCancel={() => setBindingAccount(null)}
        onOk={() => deviceForm.submit()}
        destroyOnClose
      >
        <Form form={deviceForm} layout="vertical" onFinish={bindDevice}>
          <Form.Item
            name="deviceId"
            label="设备号"
            rules={[
              { required: true, message: '请输入设备号' },
              { whitespace: true, message: '设备号不能为空' },
            ]}
          >
            <Input placeholder="例如 device-1" autoComplete="off" />
          </Form.Item>
        </Form>
      </Modal>
    </DataPage>
  );
}

export function AccountsPage() {
  return (
    <AccountManagementPage
      title="管理员管理"
      createLabel="新建管理员"
      modalTitle="新建后台管理员"
      defaultRoles={['OPERATOR']}
      roleOptions={[
        { value: 'ADMIN', label: '超级管理员' },
        { value: 'OPERATOR', label: '运营人员' },
      ]}
      roles={['ADMIN', 'OPERATOR']}
      successMessage="管理员已创建"
    />
  );
}

export function DesktopUsersPage() {
  return (
    <AccountManagementPage
      title="用户管理"
      createLabel="新建桌面端用户"
      modalTitle="新建桌面端用户"
      defaultRoles={['DESKTOP_USER']}
      roleOptions={[{ value: 'DESKTOP_USER', label: '桌面端用户' }]}
      roles={['DESKTOP_USER']}
      successMessage="桌面端用户已创建"
    />
  );
}
