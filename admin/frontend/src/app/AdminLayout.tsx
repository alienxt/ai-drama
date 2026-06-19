import {
  AppstoreOutlined,
  CloudServerOutlined,
  ControlOutlined,
  DatabaseOutlined,
  DesktopOutlined,
  DownloadOutlined,
  ExperimentOutlined,
  FileSearchOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PlaySquareOutlined,
  ProfileOutlined,
  SettingOutlined,
  SolutionOutlined,
  TeamOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { Avatar, Button, Dropdown, Layout, Menu, Typography } from 'antd';
import type { MenuProps } from 'antd';
import { useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { tokenStore } from '../shared/http';

const { Header, Content, Sider } = Layout;

type NavItem = {
  key: string;
  icon: JSX.Element;
  label: string;
  group: string;
  description: string;
};

const navItems: NavItem[] = [
  { key: '/', icon: <AppstoreOutlined />, label: '运营总览', group: '工作台', description: '关键指标与系统运行概览' },
  { key: '/dramas', icon: <DatabaseOutlined />, label: '短剧库', group: '内容资产', description: '短剧入库、分类、状态与素材信息' },
  { key: '/categories', icon: <ControlOutlined />, label: '短剧分类', group: '内容资产', description: '维护桌面端与分发策略共用的内容分类' },
  { key: '/media-accounts', icon: <PlaySquareOutlined />, label: '媒体号矩阵', group: '分发运营', description: '管理发布账号、登录态与分发策略' },
  { key: '/desktop-users', icon: <DesktopOutlined />, label: '用户管理', group: '分发运营', description: '管理桌面端登录用户与本机处理账号' },
  { key: '/tasks', icon: <CloudServerOutlined />, label: '任务监控', group: '分发运营', description: '查看分发队列、进度、失败与重试' },
  { key: '/ai-tasks', icon: <ExperimentOutlined />, label: 'AI任务', group: '分发运营', description: '查看 AI 调用、Prompt、请求响应与关联主体' },
  { key: '/accounts', icon: <SolutionOutlined />, label: '管理员管理', group: '系统管理', description: '管理后台登录账号与操作权限' },
  { key: '/desktop-versions', icon: <DownloadOutlined />, label: '桌面版本', group: '系统管理', description: '管理 macOS 与 Windows 桌面端安装包发布' },
  { key: '/configs', icon: <SettingOutlined />, label: '系统配置', group: '系统管理', description: '维护云盘、分发节奏与安全配置' },
  { key: '/request-logs', icon: <FileSearchOutlined />, label: '请求日志', group: '系统管理', description: '查看后台与桌面端 API 请求记录' },
  { key: '/exception-logs', icon: <WarningOutlined />, label: '异常日志', group: '系统管理', description: '查看接口异常、错误码与堆栈摘要' },
];

const moduleIcons: Record<string, JSX.Element> = {
  工作台: <AppstoreOutlined />,
  内容资产: <DatabaseOutlined />,
  分发运营: <PlaySquareOutlined />,
  系统管理: <SettingOutlined />,
};

const moduleItems = Array.from(new Set(navItems.map((item) => item.group))).map((group) => ({
  key: group,
  icon: moduleIcons[group],
  label: group,
}));

function getActiveNav(pathname: string) {
  return navItems.find((item) => item.key === pathname) ?? navItems[0];
}

export function AdminLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const activeNav = getActiveNav(location.pathname);
  const sideItems = navItems
    .filter((item) => item.group === activeNav.group)
    .map((item) => ({ key: item.key, icon: item.icon, label: item.label }));
  const handleLogout = () => {
    tokenStore.clear();
    navigate('/login');
  };
  const accountMenuItems: MenuProps['items'] = [
    { key: 'profile', icon: <ProfileOutlined />, label: '修改个人信息', onClick: () => navigate('/accounts') },
    { type: 'divider' },
    { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', danger: true, onClick: handleLogout },
  ];

  return (
    <Layout className="admin-shell">
      <Header className="admin-topbar">
        <div className="brand">
          <div className="brand-mark">
            <img src="/app-icon.svg" alt="AI Drama" />
          </div>
          <div>
            <Typography.Text className="brand-title">AI Drama</Typography.Text>
            <Typography.Text className="brand-subtitle">短剧分发后台</Typography.Text>
          </div>
        </div>
        <Menu
          className="module-menu"
          theme="dark"
          mode="horizontal"
          selectedKeys={[activeNav.group]}
          items={moduleItems}
          onClick={({ key }) => {
            const first = navItems.find((item) => item.group === key);
            if (first) navigate(first.key);
          }}
        />
        <div className="topbar-account">
          <Dropdown
            menu={{ items: accountMenuItems }}
            placement="bottomRight"
            trigger={['click']}
            overlayClassName="account-dropdown"
          >
            <Button
              type="text"
              className="account-avatar-button"
              aria-label="账户菜单"
              icon={<Avatar className="admin-avatar" icon={<TeamOutlined />} />}
            />
          </Dropdown>
        </div>
      </Header>
      <Layout className="admin-body">
        <Sider className="admin-sider" width={240} collapsedWidth={76} collapsed={collapsed} trigger={null}>
          <div className="side-module">
            <div className="side-module-text">
              <Typography.Title level={3} className="side-title">
                {activeNav.group}
              </Typography.Title>
            </div>
          </div>
          <Menu
            className="admin-menu"
            theme="light"
            mode="inline"
            selectedKeys={[activeNav.key]}
            items={sideItems}
            onClick={({ key }) => navigate(key)}
          />
          <Button
            className="side-collapse"
            type="text"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed((value) => !value)}
          >
            {collapsed ? null : '收起菜单'}
          </Button>
        </Sider>
        <Layout className="admin-main">
          <Header className="admin-pagebar">
            <Typography.Title level={2} className="admin-pagebar-title">
              {activeNav.label}
            </Typography.Title>
            <Typography.Text className="admin-pagebar-description">{activeNav.description}</Typography.Text>
          </Header>
          <Content className="admin-content">
            <div className="content-surface">
              <Outlet />
            </div>
          </Content>
        </Layout>
      </Layout>
    </Layout>
  );
}
