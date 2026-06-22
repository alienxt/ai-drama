import { CloseCircleOutlined, PlusCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Progress, Space, Tag, Tooltip } from 'antd';
import { useState } from 'react';
import { AdminTable } from '../../components/AdminTable';
import { DataPage } from '../../components/DataPage';
import { TableToolbar } from '../../components/TableToolbar';
import { appMessage } from '../../shared/appMessage';
import { formatDateTime } from '../../shared/format';
import { apiGetPage, apiPost } from '../../shared/http';
import { distributionTaskStatusColors, distributionTaskStatusLabel, distributionTaskStatusOptions } from '../../shared/labels';
import type { DistributionTask } from '../../shared/types';

export function TasksPage() {
  const [version, setVersion] = useState(0);
  const [filters, setFilters] = useState<Record<string, unknown>>({});

  async function generate() {
    const result = await apiPost<DistributionTask[]>('/admin/distribution-tasks/generate');
    appMessage.success(`已生成 ${result.length} 个任务`);
    setVersion((value) => value + 1);
  }

  async function action(id: string, name: 'retry' | 'cancel') {
    await apiPost(`/admin/distribution-tasks/${id}/${name}`);
    appMessage.success(name === 'retry' ? '任务已重试' : '任务已取消');
    setVersion((value) => value + 1);
  }

  return (
    <DataPage
      title="分发任务"
      actions={<Button type="primary" icon={<PlusCircleOutlined />} onClick={generate}>生成任务</Button>}
      extra={(
        <TableToolbar
          fields={[
            { name: 'keyword', placeholder: '搜索任务/媒体号/短剧', width: 240 },
            {
              name: 'status',
              placeholder: '状态',
              type: 'select',
              options: distributionTaskStatusOptions,
            },
          ]}
          onSearch={setFilters}
        />
      )}
    >
      <AdminTable<DistributionTask>
        rowKey="id"
        reloadKey={`${version}-${JSON.stringify(filters)}`}
        loadPage={(page, size) => apiGetPage<DistributionTask>('/admin/distribution-tasks', page, size, filters as Record<string, string | number | boolean | string[] | undefined>)}
        columns={[
          { title: '任务', dataIndex: 'id', render: (id: string) => <span className="mono-id">{id}</span> },
          { title: '媒体号', dataIndex: 'mediaAccountName' },
          { title: '短剧', dataIndex: 'dramaTitle' },
          {
            title: '状态',
            dataIndex: 'status',
            render: (status: DistributionTask['status']) => (
              <Tag color={distributionTaskStatusColors[status]}>{distributionTaskStatusLabel(status)}</Tag>
            ),
          },
          { title: '进度', dataIndex: 'progress', render: (value: number) => <Progress percent={value} size="small" /> },
          { title: '失败原因', dataIndex: 'failureReason' },
          { title: '创建时间', dataIndex: 'createdAt', width: 180, render: formatDateTime },
          { title: '结束时间', dataIndex: 'finishedAt', width: 180, render: formatDateTime },
          {
            title: '操作',
            render: (_, record) => (
              <Space size={4}>
                <Tooltip title="重试">
                  <Button className="table-action" size="small" type="text" icon={<ReloadOutlined />} onClick={() => action(record.id, 'retry')} />
                </Tooltip>
                <Tooltip title="取消">
                  <Button className="table-action" size="small" type="text" danger icon={<CloseCircleOutlined />} onClick={() => action(record.id, 'cancel')} />
                </Tooltip>
              </Space>
            ),
          },
        ]}
      />
    </DataPage>
  );
}
