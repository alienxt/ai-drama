import { CloseCircleOutlined, EditOutlined, PlusCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Checkbox, Form, Input, InputNumber, Modal, Select, Space, Tag, Tooltip } from 'antd';
import { useEffect, useState } from 'react';
import { AdminTable } from '../../components/AdminTable';
import { DataPage } from '../../components/DataPage';
import { TableToolbar } from '../../components/TableToolbar';
import { appMessage } from '../../shared/appMessage';
import { formatDateTime } from '../../shared/format';
import { apiGet, apiGetPage, apiPatch, apiPost } from '../../shared/http';
import { distributionTaskStatusColors, distributionTaskStatusLabel, distributionTaskStatusOptions, mediaPlatformLabel } from '../../shared/labels';
import type { DistributionTask, DistributionTaskStatusCount } from '../../shared/types';

type TaskStatusFormValues = {
  status: DistributionTask['status'];
  progress: number;
  failureReason?: string;
  clearPlatformPublishMarker?: boolean;
};

export function TasksPage() {
  const [version, setVersion] = useState(0);
  const [filters, setFilters] = useState<Record<string, unknown>>({});
  const [stats, setStats] = useState<DistributionTaskStatusCount[]>([]);
  const [editingStatusTask, setEditingStatusTask] = useState<DistributionTask | null>(null);
  const [statusSaving, setStatusSaving] = useState(false);
  const [statusForm] = Form.useForm<TaskStatusFormValues>();
  const statsKeyword = String(filters.keyword ?? '').trim();

  useEffect(() => {
    let ignore = false;

    async function loadStats() {
      const result = await apiGet<DistributionTaskStatusCount[]>(taskStatsPath(statsKeyword));
      if (!ignore) {
        setStats(result);
      }
    }

    loadStats().catch(() => {
      if (!ignore) {
        setStats([]);
      }
    });

    return () => {
      ignore = true;
    };
  }, [statsKeyword, version]);

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

  function openStatusEditor(task: DistributionTask) {
    setEditingStatusTask(task);
    statusForm.setFieldsValue({
      status: task.status,
      progress: task.progress ?? defaultProgressForStatus(task.status),
      failureReason: task.failureReason || '',
      clearPlatformPublishMarker: false,
    });
  }

  async function updateTaskStatus(values: TaskStatusFormValues) {
    if (!editingStatusTask) {
      return;
    }
    setStatusSaving(true);
    try {
      await apiPatch(`/admin/distribution-tasks/${editingStatusTask.id}/status`, values);
      appMessage.success('任务状态已更新');
      setEditingStatusTask(null);
      setVersion((value) => value + 1);
    } finally {
      setStatusSaving(false);
    }
  }

  return (
    <>
      <DataPage
        title="分发任务"
        actions={<Button type="primary" icon={<PlusCircleOutlined />} onClick={generate}>生成任务</Button>}
        extra={(
          <div className="task-monitor-tools">
            <TaskStatusOverview stats={stats} />
            <TableToolbar
              fields={[
                { name: 'keyword', placeholder: '搜索任务/账户/媒体号/短剧', width: 260 },
                {
                  name: 'status',
                  placeholder: '状态',
                  type: 'select',
                  options: distributionTaskStatusOptions,
                },
              ]}
              onSearch={setFilters}
            />
          </div>
        )}
      >
        <AdminTable<DistributionTask>
          rowKey="id"
          scroll={{ x: 1740 }}
          reloadKey={`${version}-${JSON.stringify(filters)}`}
          loadPage={(page, size) => apiGetPage<DistributionTask>('/admin/distribution-tasks', page, size, filters as Record<string, string | number | boolean | string[] | undefined>)}
          columns={[
            { title: '任务', dataIndex: 'id', width: 190, render: (id: string) => <span className="mono-id">{id}</span> },
            { title: '所属账户', dataIndex: 'ownerUsername', width: 130, render: (_: string | undefined, record) => record.ownerUsername || record.ownerAccountId || '-' },
            { title: '媒体号', dataIndex: 'mediaAccountName', width: 180, render: renderTaskCellText },
            { title: '平台', dataIndex: 'platform', width: 100, render: (platform?: string) => <Tag>{mediaPlatformLabel(platform || '')}</Tag> },
            { title: '短剧', dataIndex: 'dramaTitle', width: 260, render: renderTaskCellText },
            {
              title: '状态',
              dataIndex: 'status',
              width: 110,
              render: (status: DistributionTask['status']) => (
                <Tag color={distributionTaskStatusColors[status]}>{distributionTaskStatusLabel(status)}</Tag>
              ),
            },
            { title: '执行链路', dataIndex: 'progress', width: 420, render: (_: number, record) => <TaskExecutionChain task={record} /> },
            { title: '失败原因', dataIndex: 'failureReason', width: 260, render: renderTaskCellText },
            { title: '创建时间', dataIndex: 'createdAt', width: 180, render: formatDateTime },
            { title: '结束时间', dataIndex: 'finishedAt', width: 180, render: formatDateTime },
            {
              title: '操作',
              width: 124,
              render: (_, record) => (
                <Space size={4}>
                  <Tooltip title="改状态">
                    <Button className="table-action" size="small" type="text" icon={<EditOutlined />} onClick={() => openStatusEditor(record)} />
                  </Tooltip>
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
      <Modal
        title={`修改任务状态${editingStatusTask?.dramaTitle ? `：${editingStatusTask.dramaTitle}` : ''}`}
        open={!!editingStatusTask}
        onCancel={() => {
          if (!statusSaving) {
            setEditingStatusTask(null);
          }
        }}
        onOk={() => statusForm.submit()}
        confirmLoading={statusSaving}
        destroyOnClose
      >
        <Form<TaskStatusFormValues> form={statusForm} layout="vertical" onFinish={updateTaskStatus}>
          <Form.Item name="status" label="任务状态" rules={[{ required: true, message: '请选择任务状态' }]}>
            <Select
              options={distributionTaskStatusOptions}
              onChange={(status: DistributionTask['status']) => {
                statusForm.setFieldValue('progress', defaultProgressForStatus(status));
                if (status === 'SUCCEEDED') {
                  statusForm.setFieldValue('failureReason', '');
                }
              }}
            />
          </Form.Item>
          <Form.Item
            name="progress"
            label="任务进度"
            rules={[{ required: true, message: '请填写任务进度' }]}
            extra="执行链路按进度判断失败位置：10 下载，70 处理，75 上传，100 完成。"
          >
            <InputNumber min={0} max={100} precision={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="failureReason" label="失败原因">
            <Input.TextArea rows={3} maxLength={300} showCount placeholder="失败/取消状态下可填写原因" />
          </Form.Item>
          <Form.Item name="clearPlatformPublishMarker" valuePropName="checked">
            <Checkbox>清除平台提交标记和发布 ID</Checkbox>
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}

function renderTaskCellText(value?: string) {
  const text = value || '-';
  return (
    <Tooltip title={text}>
      <span className="task-table-cell-text">{text}</span>
    </Tooltip>
  );
}

function taskStatsPath(keyword: string) {
  const params = new URLSearchParams();
  if (keyword) {
    params.set('keyword', keyword);
  }
  const query = params.toString();
  return query ? `/admin/distribution-tasks/stats?${query}` : '/admin/distribution-tasks/stats';
}

function defaultProgressForStatus(status: DistributionTask['status']) {
  const progressByStatus: Record<DistributionTask['status'], number> = {
    PENDING: 0,
    CLAIMED: 0,
    DOWNLOADING: 10,
    PROCESSING: 70,
    UPLOADING: 75,
    SUCCEEDED: 100,
    FAILED: 70,
    CANCELLED: 70,
  };
  return progressByStatus[status] ?? 0;
}

function TaskStatusOverview({ stats }: { stats: DistributionTaskStatusCount[] }) {
  const countByStatus = new Map(stats.map((item) => [item.status, item.count]));
  const total = stats.reduce((sum, item) => sum + item.count, 0);

  return (
    <div className="task-status-overview">
      <div className="task-status-total">
        <span>全部任务</span>
        <strong>{total}</strong>
      </div>
      {distributionTaskStatusOptions.map((option) => {
        const status = option.value as DistributionTask['status'];
        return (
          <div className="task-status-item" key={status}>
            <Tag color={distributionTaskStatusColors[status]}>{option.label}</Tag>
            <strong>{countByStatus.get(status) ?? 0}</strong>
          </div>
        );
      })}
    </div>
  );
}

function TaskExecutionChain({ task }: { task: DistributionTask }) {
  const labels = taskChainLabels(task);
  return (
    <div className="task-execution-chain" title={taskChainSummary(task)}>
      {labels.map((label, index) => {
        const state = taskChainState(task, index);
        return (
          <span className="task-chain-fragment" key={`${label}-${index}`}>
            <span className={`task-chain-step task-chain-step-${state}`}>{label}</span>
            {index < labels.length - 1 ? (
              <span className={`task-chain-connector task-chain-connector-${taskChainConnectorState(task, index)}`} />
            ) : null}
          </span>
        );
      })}
    </div>
  );
}

function taskChainLabels(task: DistributionTask) {
  const labels = ['排队', '领取', '下载', '处理', '上传', '完成'];
  if (task.status === 'FAILED') {
    labels[taskChainProblemStep(task)] += '失败';
  } else if (task.status === 'CANCELLED') {
    labels[taskChainProblemStep(task)] += '停止';
  } else if (['DOWNLOADING', 'UPLOADING', 'PROCESSING'].includes(task.status)) {
    labels[taskChainActiveStep(task)] += '中';
  }
  return labels;
}

function taskChainState(task: DistributionTask, step: number) {
  if (task.status === 'SUCCEEDED') {
    return 'done';
  }
  if (task.status === 'FAILED') {
    const failedStep = taskChainProblemStep(task);
    if (step < failedStep) {
      return 'done';
    }
    return step === failedStep ? 'failed' : 'waiting';
  }
  if (task.status === 'CANCELLED') {
    const stoppedStep = taskChainProblemStep(task);
    if (step < stoppedStep) {
      return 'done';
    }
    return step === stoppedStep ? 'cancelled' : 'waiting';
  }
  const activeStep = taskChainActiveStep(task);
  if (step < activeStep) {
    return 'done';
  }
  if (step === activeStep) {
    return 'active';
  }
  return 'waiting';
}

function taskChainConnectorState(task: DistributionTask, step: number) {
  const currentState = taskChainState(task, step);
  const nextState = taskChainState(task, step + 1);
  if (currentState === 'done' && nextState !== 'waiting') {
    return 'done';
  }
  if (nextState === 'done') {
    return 'done';
  }
  return 'waiting';
}

function taskChainSummary(task: DistributionTask) {
  const labels = taskChainLabels(task);
  const states = labels.map((_, index) => taskChainState(task, index));
  const failedIndex = states.indexOf('failed');
  if (failedIndex >= 0) {
    return labels[failedIndex];
  }
  const cancelledIndex = states.indexOf('cancelled');
  if (cancelledIndex >= 0) {
    return labels[cancelledIndex];
  }
  if (task.status === 'SUCCEEDED') {
    return '已完成';
  }
  const activeIndex = states.indexOf('active');
  return activeIndex >= 0 ? labels[activeIndex] : '-';
}

function taskChainActiveStep(task: DistributionTask) {
  const statusSteps: Record<DistributionTask['status'], number> = {
    PENDING: 0,
    CLAIMED: 1,
    DOWNLOADING: 2,
    PROCESSING: 3,
    UPLOADING: 4,
    SUCCEEDED: 5,
    FAILED: taskChainProblemStep(task),
    CANCELLED: taskChainProblemStep(task),
  };
  return statusSteps[task.status] ?? taskChainProblemStep(task);
}

function taskChainProblemStep(task: DistributionTask) {
  const progress = Number(task.progress || 0);
  if (progress >= 75) {
    return 4;
  }
  if (progress >= 70) {
    return 3;
  }
  if (progress >= 10) {
    return 2;
  }
  if (task.status === 'PENDING') {
    return 0;
  }
  return 1;
}
