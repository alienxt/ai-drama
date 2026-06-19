import React from 'react';
import ReactDOM from 'react-dom/client';
import { ConfigProvider, App as AntApp } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { AppRouter } from './app/AppRouter';
import { ErrorBoundary } from './app/ErrorBoundary';
import { AppMessageBridge } from './shared/appMessage';
import './styles/global.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          borderRadius: 6,
          colorPrimary: '#2563eb',
          fontSize: 13,
        },
        components: {
          Layout: {
            siderBg: '#111827',
            triggerBg: '#111827',
          },
        },
      }}
    >
      <AntApp message={{ maxCount: 3, duration: 2.5 }}>
        <AppMessageBridge />
        <ErrorBoundary>
          <AppRouter />
        </ErrorBoundary>
      </AntApp>
    </ConfigProvider>
  </React.StrictMode>,
);
