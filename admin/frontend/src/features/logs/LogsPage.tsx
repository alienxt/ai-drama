import { Button, Modal, Space, Tag, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { AdminTable } from '../../components/AdminTable';
import { DataPage } from '../../components/DataPage';
import { TableToolbar } from '../../components/TableToolbar';
import { formatDateTime } from '../../shared/format';
import { apiGetPage } from '../../shared/http';
import type { ExceptionLog, HongguoApiDebugLog, RequestLog } from '../../shared/types';

const methodOptions = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((method) => ({
  value: method,
  label: method,
}));

function statusColor(status: number) {
  if (status >= 500) return 'red';
  if (status >= 400) return 'orange';
  if (status >= 300) return 'blue';
  return 'green';
}

function LogToolbar({ onSearch }: { onSearch: (values: Record<string, unknown>) => void }) {
  return (
    <TableToolbar
      fields={[
        { name: 'keyword', placeholder: '搜索路径/用户/IP/UA', width: 240 },
        { name: 'method', placeholder: '方法', type: 'select', options: methodOptions, width: 120 },
        { name: 'status', placeholder: '状态码', type: 'number', width: 120 },
        { name: 'traceId', placeholder: 'Trace ID', width: 260 },
      ]}
      onSearch={onSearch}
    />
  );
}

function requestText(record: { source?: string; method?: string; path?: string; query?: string }) {
  if (!record.path) {
    return record.source || '-';
  }
  return record.query ? `${record.path}?${record.query}` : record.path;
}

function shortId(value?: string) {
  if (!value) {
    return '-';
  }
  return value.length > 18 ? `${value.slice(0, 8)}...${value.slice(-6)}` : value;
}

function CompactText({ value, className }: { value?: string; className?: string }) {
  if (!value) {
    return <span className="muted">-</span>;
  }
  return (
    <Tooltip title={value}>
      <Typography.Text className={className} ellipsis>
        {value}
      </Typography.Text>
    </Tooltip>
  );
}

function TraceId({ value }: { value?: string }) {
  if (!value) {
    return <span className="muted">-</span>;
  }
  return (
    <Tooltip title={value}>
      <Typography.Text copyable={{ text: value }} className="mono-id log-trace-id">
        {shortId(value)}
      </Typography.Text>
    </Tooltip>
  );
}

function prettyText(value?: string) {
  if (!value) {
    return '-';
  }
  try {
    return JSON.stringify(JSON.parse(value), null, 2);
  } catch {
    return value;
  }
}

function RequestCell({ record }: { record: { source?: string; method?: string; path?: string; query?: string } }) {
  const text = requestText(record);
  return (
    <Space className="log-request" size={8}>
      {record.method ? <Tag className="log-method-tag">{record.method}</Tag> : null}
      <Tooltip title={text}>
        <Typography.Text copyable={text !== '-' ? { text } : false} className="mono-id log-request-path" ellipsis>
          {text}
        </Typography.Text>
      </Tooltip>
    </Space>
  );
}

function baseColumns<T extends RequestLog | ExceptionLog>(): ColumnsType<T> {
  return [
    {
      title: '时间',
      dataIndex: 'createdAt',
      width: 168,
      render: (value: string) => formatDateTime(value),
    },
    {
      title: 'Trace ID',
      dataIndex: 'traceId',
      width: 160,
      render: (value?: string) => <TraceId value={value} />,
    },
    {
      title: '请求',
      width: 360,
      render: (_, record) => <RequestCell record={record} />,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 82,
      render: (status: number) => <Tag color={statusColor(status)}>{status}</Tag>,
    },
    {
      title: '用户',
      dataIndex: 'username',
      width: 112,
      render: (value?: string) => <CompactText value={value} />,
    },
    {
      title: 'IP',
      dataIndex: 'clientIp',
      width: 128,
      render: (value?: string) => <CompactText value={value} />,
    },
    {
      title: 'UA',
      dataIndex: 'userAgent',
      width: 180,
      ellipsis: true,
      render: (value?: string) => <CompactText value={value} className="log-muted-text" />,
    },
  ];
}

function cleanFilters(filters: Record<string, unknown>) {
  return filters as Record<string, string | number | boolean | string[] | undefined>;
}

export function RequestLogsPage() {
  const [filters, setFilters] = useState<Record<string, unknown>>({});

  return (
    <DataPage title="请求日志" extra={<LogToolbar onSearch={setFilters} />}>
      <AdminTable<RequestLog>
        rowKey="id"
        className="log-table"
        tableLayout="fixed"
        scroll={{ x: 1180 }}
        reloadKey={JSON.stringify(filters)}
        loadPage={(page, size) => apiGetPage<RequestLog>('/admin/request-logs', page, size, cleanFilters(filters))}
        columns={[
          ...baseColumns<RequestLog>(),
          {
            title: '耗时',
            dataIndex: 'durationMs',
            width: 100,
            render: (value: number) => `${value} ms`,
          },
        ]}
      />
    </DataPage>
  );
}

export function ExceptionLogsPage() {
  const [filters, setFilters] = useState<Record<string, unknown>>({});

  return (
    <DataPage title="异常日志" extra={<LogToolbar onSearch={setFilters} />}>
      <AdminTable<ExceptionLog>
        rowKey="id"
        className="log-table exception-log-table"
        tableLayout="fixed"
        scroll={{ x: 1480 }}
        reloadKey={JSON.stringify(filters)}
        loadPage={(page, size) => apiGetPage<ExceptionLog>('/admin/exception-logs', page, size, cleanFilters(filters))}
        columns={[
          ...baseColumns<ExceptionLog>(),
          {
            title: '来源',
            dataIndex: 'source',
            width: 96,
            render: (value?: string) => <Tag>{value || 'HTTP'}</Tag>,
          },
          {
            title: '错误码',
            dataIndex: 'code',
            width: 210,
            render: (value: string) => <CompactText value={value} className="log-error-code" />,
          },
          {
            title: '异常',
            dataIndex: 'exceptionClass',
            width: 260,
            ellipsis: true,
            render: (value: string) => <CompactText value={value} className="mono-id log-exception-class" />,
          },
          {
            title: '消息',
            dataIndex: 'message',
            width: 360,
            ellipsis: true,
            render: (value: string, record) => (
              <Tooltip title={record.stackTrace || value}>
                <Typography.Text className="log-message" ellipsis>{value}</Typography.Text>
              </Tooltip>
            ),
          },
        ]}
      />
    </DataPage>
  );
}

export function HongguoApiDebugLogsPage() {
  const [filters, setFilters] = useState<Record<string, unknown>>({});
  const [viewing, setViewing] = useState<HongguoApiDebugLog | null>(null);

  return (
    <DataPage title="红果接口日志" extra={<LogToolbar onSearch={setFilters} />}>
      <AdminTable<HongguoApiDebugLog>
        rowKey="id"
        className="log-table hongguo-api-log-table"
        tableLayout="fixed"
        scroll={{ x: 1500 }}
        reloadKey={JSON.stringify(filters)}
        loadPage={(page, size) => apiGetPage<HongguoApiDebugLog>('/admin/hongguo-api-debug-logs', page, size, cleanFilters(filters))}
        columns={[
          {
            title: '时间',
            dataIndex: 'createdAt',
            width: 168,
            render: (value: string) => formatDateTime(value),
          },
          {
            title: 'Trace ID',
            dataIndex: 'traceId',
            width: 160,
            render: (value?: string) => <TraceId value={value} />,
          },
          {
            title: '方法',
            dataIndex: 'method',
            width: 82,
            render: (method: string) => <Tag className="log-method-tag">{method}</Tag>,
          },
          {
            title: '接口',
            dataIndex: 'endpoint',
            width: 120,
            render: (value?: string) => <CompactText value={value} className="mono-id" />,
          },
          {
            title: '状态',
            dataIndex: 'status',
            width: 82,
            render: (status: number) => <Tag color={statusColor(status)}>{status}</Tag>,
          },
          {
            title: '耗时',
            dataIndex: 'durationMs',
            width: 100,
            render: (value: number) => `${value} ms`,
          },
          {
            title: '请求 URL',
            dataIndex: 'requestUrl',
            width: 420,
            render: (value?: string) => <CompactText value={value} className="mono-id log-request-path" />,
          },
          {
            title: '错误',
            dataIndex: 'errorMessage',
            width: 240,
            render: (value?: string) => <CompactText value={value} className="log-error-code" />,
          },
          {
            title: '详情',
            width: 90,
            fixed: 'right',
            render: (_, record) => <Button size="small" onClick={() => setViewing(record)}>查看</Button>,
          },
        ]}
      />
      <Modal
        title="红果接口日志详情"
        open={!!viewing}
        onCancel={() => setViewing(null)}
        footer={<Button type="primary" onClick={() => setViewing(null)}>关闭</Button>}
        width={960}
      >
        <Space direction="vertical" size={16} className="hongguo-api-log-detail">
          <div>
            <Typography.Text strong>请求 URL</Typography.Text>
            <Typography.Paragraph copyable className="mono-id log-detail-block">
              {viewing?.requestUrl || '-'}
            </Typography.Paragraph>
          </div>
          <div>
            <Typography.Text strong>请求体</Typography.Text>
            <Typography.Paragraph copyable className="mono-id log-detail-block">
              {prettyText(viewing?.requestBody)}
            </Typography.Paragraph>
          </div>
          <div>
            <Typography.Text strong>返回内容</Typography.Text>
            <Typography.Paragraph copyable className="mono-id log-detail-block">
              {prettyText(viewing?.responseBody)}
            </Typography.Paragraph>
          </div>
          {viewing?.errorMessage ? (
            <div>
              <Typography.Text strong>错误信息</Typography.Text>
              <Typography.Paragraph copyable className="mono-id log-detail-block">
                {viewing.errorMessage}
              </Typography.Paragraph>
            </div>
          ) : null}
        </Space>
      </Modal>
    </DataPage>
  );
}
