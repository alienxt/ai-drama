import type { ReactNode } from 'react';

export function DataPage({
  title,
  extra,
  actions,
  children,
}: {
  title: string;
  extra?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="page">
      <div className="page-header">
        <h1 className="page-title">{title}</h1>
      </div>
      {extra ? <div className="page-tools">{extra}</div> : null}
      {actions ? <div className="page-actions">{actions}</div> : null}
      <div className="page-table">{children}</div>
    </section>
  );
}
