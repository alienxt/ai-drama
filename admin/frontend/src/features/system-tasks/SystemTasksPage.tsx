import { EyeOutlined } from '@ant-design/icons';
import { Button, Descriptions, Modal, Space, Statistic, Table, Tag, Typography } from 'antd';
import { useState } from 'react';
import { AdminTable } from '../../components/AdminTable';
import { DataPage } from '../../components/DataPage';
import { TableToolbar } from '../../components/TableToolbar';
import { formatDateTime } from '../../shared/format';
import { apiGetPage } from '../../shared/http';
import {
  systemTaskStatusColors,
  systemTaskStatusLabel,
  systemTaskStatusOptions,
  systemTaskTypeLabel,
  systemTaskTypeOptions,
} from '../../shared/labels';
import type { SystemTask } from '../../shared/types';

type DramaSummary = {
  id?: string;
  title?: string;
  sourcePath?: string;
  episodeCount?: number;
  status?: string;
};

function asNumber(value: unknown) {
  return typeof value === 'number' ? value : 0;
}

function asDramaSummaries(value: unknown): DramaSummary[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is DramaSummary => typeof item === 'object' && item !== null);
}

function JsonBlock({ value }: { value?: unknown }) {
  if (value == null || value === '') {
    return <Typography.Text type="secondary">-</Typography.Text>;
  }
  return <pre className="json-block">{typeof value === 'string' ? value : JSON.stringify(value, null, 2)}</pre>;
}

function taskDuration(value?: number) {
  if (value == null) {
    return '-';
  }
  return value >= 1000 ? `${(value / 1000).toFixed(1)} s` : `${value} ms`;
}

function taskTrigger(value?: string) {
  if (value === 'manual') {
    return '手动触发';
  }
  if (value === 'scheduled') {
    return '定时触发';
  }
  return value || '-';
}

function BaiduScanResult({ task }: { task: SystemTask }) {
  const result = task.resultPayload ?? {};
  const dramas = asDramaSummaries(result.dramas);

  return (
    <section className="system-task-detail-section">
      <Typography.Title level={5}>扫描结果</Typography.Title>
      <div className="system-task-metrics">
        <Statistic title="导入短剧" value={asNumber(result.importedCount)} suffix="部" />
        <Statistic title="准备成功" value={asNumber(result.preparedCount)} suffix="部" />
        <Statistic title="准备失败" value={asNumber(result.prepareFailedCount)} suffix="部" />
      </div>
      <Table<DramaSummary>
        className="system-task-drama-table"
        rowKey={(record, index) => record.id || record.sourcePath || String(index)}
        size="small"
        pagination={false}
        dataSource={dramas}
        columns={[
          { title: '短剧', dataIndex: 'title', render: (value?: string) => value || '-' },
          { title: '集数', dataIndex: 'episodeCount', width: 80, render: (value?: number) => value ?? 0 },
          { title: '状态', dataIndex: 'status', width: 100, render: (value?: string) => value || '-' },
          {
            title: '来源路径',
            dataIndex: 'sourcePath',
            ellipsis: true,
            render: (value?: string) => value ? <Typography.Text copyable className="mono-id">{value}</Typography.Text> : '-',
          },
        ]}
      />
    </section>
  );
}

function cleanFilters(filters: Record<string, unknown>) {
  return filters as Record<string, string | number | boolean | string[] | undefined>;
}

export function SystemTasksPage() {
  const [filters, setFilters] = useState<Record<string, unknown>>({});
  const [active, setActive] = useState<SystemTask | null>(null);

  return (
    <DataPage
      title="系统任务"
      extra={(
        <TableToolbar
          fields={[
            { name: 'keyword', placeholder: '搜索任务/摘要/错误', width: 260 },
            { name: 'type', placeholder: '任务类型', type: 'select', options: systemTaskTypeOptions },
            { name: 'status', placeholder: '状态', type: 'select', options: systemTaskStatusOptions },
          ]}
          onSearch={setFilters}
        />
      )}
    >
      <AdminTable<SystemTask>
        rowKey="id"
        reloadKey={JSON.stringify(filters)}
        loadPage={(page, size) => apiGetPage<SystemTask>('/admin/system-tasks', page, size, cleanFilters(filters))}
        columns={[
          { title: '任务', dataIndex: 'title', render: (value: string, record) => value || systemTaskTypeLabel(record.type) },
          { title: '类型', dataIndex: 'type', render: (type: string) => systemTaskTypeLabel(type) },
          {
            title: '状态',
            dataIndex: 'status',
            render: (status: SystemTask['status']) => (
              <Tag color={systemTaskStatusColors[status]}>{systemTaskStatusLabel(status)}</Tag>
            ),
          },
          { title: '触发', dataIndex: 'triggerSource', render: taskTrigger },
          { title: '结果摘要', dataIndex: 'summary', render: (value: string | undefined, record) => value || record.errorMessage || '-' },
          { title: '耗时', dataIndex: 'durationMs', width: 110, render: taskDuration },
          { title: '开始时间', dataIndex: 'startedAt', width: 170, render: formatDateTime },
          {
            title: '操作',
            width: 90,
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
        title="系统任务详情"
        open={!!active}
        footer={null}
        width={960}
        onCancel={() => setActive(null)}
      >
        {active ? (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="任务ID">{active.id}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={systemTaskStatusColors[active.status]}>{systemTaskStatusLabel(active.status)}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="类型">{systemTaskTypeLabel(active.type)}</Descriptions.Item>
              <Descriptions.Item label="触发">{taskTrigger(active.triggerSource)}</Descriptions.Item>
              <Descriptions.Item label="开始时间">{formatDateTime(active.startedAt)}</Descriptions.Item>
              <Descriptions.Item label="结束时间">{formatDateTime(active.finishedAt)}</Descriptions.Item>
              <Descriptions.Item label="耗时">{taskDuration(active.durationMs)}</Descriptions.Item>
              <Descriptions.Item label="错误">{active.errorMessage || '-'}</Descriptions.Item>
            </Descriptions>
            {active.type === 'BAIDU_PAN_SCAN' ? <BaiduScanResult task={active} /> : null}
            <Typography.Title level={5}>请求参数</Typography.Title>
            <JsonBlock value={active.requestPayload} />
            <Typography.Title level={5}>结果数据</Typography.Title>
            <JsonBlock value={active.resultPayload} />
          </Space>
        ) : null}
      </Modal>
    </DataPage>
  );
}
