import { Card, Col, Row, Statistic } from 'antd';
import { DataPage } from '../../components/DataPage';

export function DashboardPage() {
  return (
    <DataPage title="运营总览">
      <Row gutter={[16, 16]}>
        <Col xs={24} md={6}><Card><Statistic title="待处理任务" value={0} /></Card></Col>
        <Col xs={24} md={6}><Card><Statistic title="活跃媒体号" value={0} /></Card></Col>
        <Col xs={24} md={6}><Card><Statistic title="短剧库存" value={0} /></Card></Col>
        <Col xs={24} md={6}><Card><Statistic title="今日成功" value={0} /></Card></Col>
      </Row>
    </DataPage>
  );
}

