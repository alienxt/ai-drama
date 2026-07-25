import { AppleOutlined, DownloadOutlined, KeyOutlined, SafetyCertificateOutlined, WindowsOutlined } from '@ant-design/icons';
import { Alert, Button, Form, Input, Space, Tag, Typography } from 'antd';
import { useMemo, useState } from 'react';
import { apiPost } from '../../shared/http';
import type { PublicDesktopDownload, PublicDownloadAccess } from '../../shared/types';

type InviteForm = {
  code: string;
};

const platformMeta: Record<PublicDesktopDownload['platform'], { label: string; icon: JSX.Element }> = {
  MAC: { label: 'macOS', icon: <AppleOutlined /> },
  WINDOWS: { label: 'Windows', icon: <WindowsOutlined /> },
};

function formatSize(size: number) {
  if (!size) return '-';
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function absoluteDownloadUrl(url?: string) {
  if (!url) return undefined;
  if (/^https?:\/\//i.test(url)) return url;
  return `${window.location.origin}${url}`;
}

function sortedDownloads(downloads: PublicDesktopDownload[]) {
  const order: Record<PublicDesktopDownload['platform'], number> = { MAC: 0, WINDOWS: 1 };
  return [...downloads].sort((left, right) => order[left.platform] - order[right.platform]);
}

export function PublicDownloadPage() {
  const [loading, setLoading] = useState(false);
  const [access, setAccess] = useState<PublicDownloadAccess | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form] = Form.useForm<InviteForm>();

  const downloads = useMemo(() => sortedDownloads(access?.downloads || []), [access]);

  async function submit(values: InviteForm) {
    setLoading(true);
    setError(null);
    try {
      const response = await apiPost<PublicDownloadAccess>('/public/download-invites/validate-all', {
        code: values.code,
      });
      setAccess(response);
    } catch (exception) {
      setAccess(null);
      setError(exception instanceof Error ? exception.message : '邀请码校验失败');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="public-download-page">
      <section className="public-download-shell">
        <div className="public-download-header">
          <div className="public-download-brand">
            <img src="/app-icon.svg" alt="AI Drama" />
            <div>
              <Typography.Title level={1}>AI Drama Desktop</Typography.Title>
              <Typography.Text>客户端安装包下载</Typography.Text>
            </div>
          </div>
          <Tag icon={<SafetyCertificateOutlined />} color="blue">邀请码下载</Tag>
        </div>

        <div className="public-download-grid">
          <div className="public-download-intro">
            <Typography.Title level={2}>下载桌面客户端</Typography.Title>
            <Typography.Paragraph>
              输入邀请码后获取当前已发布的 macOS 与 Windows 客户端安装包。
            </Typography.Paragraph>
          </div>

          <div className="public-download-panel">
            <Form form={form} layout="vertical" onFinish={submit} requiredMark={false}>
              <Form.Item
                name="code"
                label="邀请码"
                rules={[{ required: true, message: '请输入邀请码' }]}
              >
                <Input
                  size="large"
                  prefix={<KeyOutlined />}
                  placeholder="请输入邀请码"
                  autoComplete="off"
                />
              </Form.Item>
              <Button type="primary" htmlType="submit" size="large" loading={loading} block>
                获取客户端
              </Button>
            </Form>
            {error ? <Alert className="public-download-alert" type="error" showIcon message={error} /> : null}
          </div>
        </div>

        {downloads.length ? (
          <div className="public-download-results">
            {downloads.map((item) => {
              const meta = platformMeta[item.platform];
              const href = absoluteDownloadUrl(item.downloadUrl);
              return (
                <div className="public-download-package" key={item.platform}>
                  <div className="public-download-package-main">
                    <div className="public-download-package-icon">{meta.icon}</div>
                    <div className="public-download-package-text">
                      <Typography.Title level={3}>{meta.label}</Typography.Title>
                      {item.available ? (
                        <Space size={8} wrap>
                          <Tag color="green">v{item.version}</Tag>
                          <Tag>{formatSize(item.fileSize)}</Tag>
                          {item.mandatory ? <Tag color="red">强制更新</Tag> : null}
                        </Space>
                      ) : (
                        <Tag>暂无安装包</Tag>
                      )}
                      {item.releaseNotes ? (
                        <Typography.Paragraph className="public-download-notes">
                          {item.releaseNotes}
                        </Typography.Paragraph>
                      ) : null}
                    </div>
                  </div>
                  <Button
                    type={item.available ? 'primary' : 'default'}
                    icon={<DownloadOutlined />}
                    href={href}
                    target="_blank"
                    disabled={!item.available || !href}
                  >
                    下载
                  </Button>
                </div>
              );
            })}
          </div>
        ) : null}
      </section>
    </main>
  );
}
