import { Table } from 'antd';
import type { TableProps } from 'antd';
import { useState } from 'react';
import type { PageResult } from '../shared/types';
import { useAsyncData } from '../shared/useAsyncData';

type AdminTableProps<T extends object> = Omit<TableProps<T>, 'dataSource' | 'loading' | 'pagination' | 'onChange'> & {
  loadPage: (page: number, size: number) => Promise<PageResult<T>>;
  reloadKey?: unknown;
};

export function AdminTable<T extends object>({ loadPage, reloadKey, ...tableProps }: AdminTableProps<T>) {
  const [current, setCurrent] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const { data, loading } = useAsyncData(() => loadPage(current - 1, pageSize), [current, pageSize, reloadKey]);

  return (
    <Table<T>
      {...tableProps}
      loading={loading}
      dataSource={data?.content ?? []}
      pagination={{
        current,
        pageSize,
        total: data?.totalElements ?? 0,
        showSizeChanger: true,
        showTotal: (total) => `共 ${total} 条`,
      }}
      onChange={(pagination) => {
        setCurrent(pagination.current ?? 1);
        setPageSize(pagination.pageSize ?? 10);
      }}
    />
  );
}
