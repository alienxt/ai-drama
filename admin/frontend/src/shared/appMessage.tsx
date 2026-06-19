import { App } from 'antd';
import { useEffect } from 'react';

type AppMessageApi = ReturnType<typeof App.useApp>['message'];

let activeMessage: AppMessageApi | null = null;

export function AppMessageBridge() {
  const { message } = App.useApp();

  useEffect(() => {
    activeMessage = message;
    return () => {
      if (activeMessage === message) {
        activeMessage = null;
      }
    };
  }, [message]);

  return null;
}

export function getErrorMessage(error: unknown, fallback = '操作失败') {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  if (typeof error === 'string' && error.trim()) {
    return error;
  }
  return fallback;
}

export const appMessage = {
  success(content: string) {
    activeMessage?.success(content);
  },
  error(error: unknown, fallback?: string) {
    activeMessage?.error(getErrorMessage(error, fallback));
  },
};
