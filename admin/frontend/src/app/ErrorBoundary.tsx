import { Result } from 'antd';
import type { ReactNode } from 'react';
import React from 'react';

type State = { hasError: boolean };

export class ErrorBoundary extends React.Component<{ children: ReactNode }, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return <Result status="500" title="页面异常" subTitle="请刷新页面，或联系管理员查看服务日志。" />;
    }
    return this.props.children;
  }
}

