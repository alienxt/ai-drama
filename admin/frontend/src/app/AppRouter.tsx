import { Navigate, RouterProvider, createBrowserRouter } from 'react-router-dom';
import { AdminLayout } from './AdminLayout';
import { tokenStore } from '../shared/http';
import { LoginPage } from '../features/auth/LoginPage';
import { DashboardPage } from '../features/dashboard/DashboardPage';
import { AccountsPage, DesktopUsersPage } from '../features/accounts/AccountsPage';
import { CategoriesPage } from '../features/categories/CategoriesPage';
import { ConfigsPage } from '../features/configs/ConfigsPage';
import { DramasPage } from '../features/dramas/DramasPage';
import { MediaAccountsPage } from '../features/media/MediaAccountsPage';
import { TasksPage } from '../features/tasks/TasksPage';
import { AiTasksPage } from '../features/ai-tasks/AiTasksPage';
import { DesktopVersionsPage } from '../features/versions/DesktopVersionsPage';
import { ExceptionLogsPage, RequestLogsPage } from '../features/logs/LogsPage';

function RequireAuth({ children }: { children: JSX.Element }) {
  return tokenStore.get() ? children : <Navigate to="/login" replace />;
}

const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    path: '/',
    element: (
      <RequireAuth>
        <AdminLayout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'accounts', element: <AccountsPage /> },
      { path: 'desktop-users', element: <DesktopUsersPage /> },
      { path: 'categories', element: <CategoriesPage /> },
      { path: 'configs', element: <ConfigsPage /> },
      { path: 'dramas', element: <DramasPage /> },
      { path: 'media-accounts', element: <MediaAccountsPage /> },
      { path: 'tasks', element: <TasksPage /> },
      { path: 'ai-tasks', element: <AiTasksPage /> },
      { path: 'desktop-versions', element: <DesktopVersionsPage /> },
      { path: 'request-logs', element: <RequestLogsPage /> },
      { path: 'exception-logs', element: <ExceptionLogsPage /> },
    ],
  },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
