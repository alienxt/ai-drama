import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { Button, Card, Form, Input, Typography } from 'antd';
import { useNavigate } from 'react-router-dom';
import { appMessage } from '../../shared/appMessage';
import { apiPost, tokenStore } from '../../shared/http';
import type { Account } from '../../shared/types';

type LoginResponse = { token: string; account: Account };

export function LoginPage() {
  const navigate = useNavigate();

  async function submit(values: { username: string; password: string }) {
    const result = await apiPost<LoginResponse>('/auth/login', values);
    tokenStore.set(result.token);
    appMessage.success(`欢迎回来，${result.account.username}`);
    navigate('/');
  }

  return (
    <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: '#f3f4f6' }}>
      <Card style={{ width: 360, borderRadius: 8 }}>
        <Typography.Title level={3} style={{ marginTop: 0 }}>
          短剧分发后台
        </Typography.Title>
        <Form layout="vertical" onFinish={submit} initialValues={{ username: 'admin', password: 'admin123' }}>
          <Form.Item name="username" label="用户名" rules={[{ required: true }]}>
            <Input prefix={<UserOutlined />} autoComplete="username" />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true }]}>
            <Input.Password prefix={<LockOutlined />} autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block>
            登录
          </Button>
        </Form>
      </Card>
    </div>
  );
}
