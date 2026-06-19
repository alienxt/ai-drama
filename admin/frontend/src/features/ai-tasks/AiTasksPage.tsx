import { EyeOutlined } from '@ant-design/icons';
import { Button, Descriptions, Modal, Space, Tag, Typography } from 'antd';
import { useState } from 'react';
import { AdminTable } from '../../components/AdminTable';
import { DataPage } from '../../components/DataPage';
import { TableToolbar } from '../../components/TableToolbar';
import { formatDateTime } from '../../shared/format';
import { apiGetPage } from '../../shared/http';
import {
  aiTaskStatusColors,
  aiTaskStatusLabel,
  aiTaskStatusOptions,
  aiTaskTypeLabel,
  aiTaskTypeOptions,
} from '../../shared/labels';
import type { AiTask } from '../../shared/types';

function JsonBlock({ value }: { value?: unknown }) {
  if (value == null || value === '') {
    return <Typography.Text type="secondary">-</Typography.Text>;
  }
  return <pre className="json-block">{typeof value === 'string' ? value : JSON.stringify(value, null, 2)}</pre>;
}

export function AiTasksPage() {
  const [filters, setFilters] = useState<Record<string, unknown>>({});
  const [active, setActive] = useState<AiTask | null>(null);

  return (
    <DataPage
      title="AI任务"
      extra={(
        <TableToolbar
          fields={[
            { name: 'keyword', placeholder: '搜索任务/短剧/Prompt/错误', width: 260 },
            { name: 'type', placeholder: '任务类型', type: 'select', options: aiTaskTypeOptions },
            { name: 'status', placeholder: '状态', type: 'select', options: aiTaskStatusOptions },
          ]}
          onSearch={setFilters}
        />
      )}
    >
      <AdminTable<AiTask>
        rowKey="id"
        reloadKey={JSON.stringify(filters)}
        loadPage={(page, size) => apiGetPage<AiTask>('/admin/ai-tasks', page, size, filters as Record<string, string | number | boolean | string[] | undefined>)}
        columns={[
          { title: '任务', dataIndex: 'id', render: (id: string) => <span className="mono-id">{id}</span> },
          { title: '类型', dataIndex: 'type', render: (type: string) => aiTaskTypeLabel(type) },
          {
            title: '状态',
            dataIndex: 'status',
            render: (status: AiTask['status']) => (
              <Tag color={aiTaskStatusColors[status]}>{aiTaskStatusLabel(status)}</Tag>
            ),
          },
          { title: '主体', dataIndex: 'subjectTitle', render: (value: string, record) => value || record.subjectId || '-' },
          { title: '模型', dataIndex: 'model' },
          { title: '耗时', dataIndex: 'durationMs', render: (value?: number) => (value == null ? '-' : `${value} ms`) },
          { title: '创建时间', dataIndex: 'createdAt', render: formatDateTime },
          {
            title: '操作',
            render: (_, record) => (
              <Space size={4}>
                <Button className="table-action" size="small" type="text" icon={<EyeOutlined />} onClick={() => setActive(record)}>
                  详情
                </Button>
              </Space>
            ),
          },
        ]}
      />
      <Modal
        title="AI任务详情"
        open={!!active}
        footer={null}
        width={880}
        onCancel={() => setActive(null)}
      >
        {active ? (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="任务ID">{active.id}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={aiTaskStatusColors[active.status]}>{aiTaskStatusLabel(active.status)}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="类型">{aiTaskTypeLabel(active.type)}</Descriptions.Item>
              <Descriptions.Item label="主体">{active.subjectTitle || active.subjectId || '-'}</Descriptions.Item>
              <Descriptions.Item label="模型">{active.model || '-'}</Descriptions.Item>
              <Descriptions.Item label="接口">{active.endpoint || '-'}</Descriptions.Item>
              <Descriptions.Item label="开始时间">{formatDateTime(active.startedAt)}</Descriptions.Item>
              <Descriptions.Item label="结束时间">{formatDateTime(active.finishedAt)}</Descriptions.Item>
              <Descriptions.Item label="耗时">{active.durationMs == null ? '-' : `${active.durationMs} ms`}</Descriptions.Item>
              <Descriptions.Item label="错误">{active.errorMessage || '-'}</Descriptions.Item>
            </Descriptions>
            <Typography.Title level={5}>Prompt</Typography.Title>
            <JsonBlock value={active.prompt} />
            <Typography.Title level={5}>请求</Typography.Title>
            <JsonBlock value={active.requestPayload} />
            <Typography.Title level={5}>响应</Typography.Title>
            <JsonBlock value={active.responsePayload} />
          </Space>
        ) : null}
      </Modal>
    </DataPage>
  );
}
