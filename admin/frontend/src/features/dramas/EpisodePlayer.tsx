import { CloudOutlined, PlayCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Empty, Spin, Tag, Tooltip, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { apiGet } from '../../shared/http';
import type { AdminEpisode, EpisodePlaySource } from '../../shared/types';

type EpisodePlayerProps = {
  dramaId: string;
};

export function EpisodePlayer({ dramaId }: EpisodePlayerProps) {
  const [episodes, setEpisodes] = useState<AdminEpisode[]>([]);
  const [loadingEpisodes, setLoadingEpisodes] = useState(false);
  const [loadingEpisodeNo, setLoadingEpisodeNo] = useState<number | null>(null);
  const [activeSource, setActiveSource] = useState<EpisodePlaySource | null>(null);

  useEffect(() => {
    void loadEpisodes();
  }, [dramaId]);

  async function loadEpisodes() {
    setLoadingEpisodes(true);
    setActiveSource(null);
    try {
      const rows = await apiGet<AdminEpisode[]>(`/admin/dramas/${dramaId}/episodes`);
      setEpisodes(rows);
    } finally {
      setLoadingEpisodes(false);
    }
  }

  async function play(episodeNo: number) {
    setLoadingEpisodeNo(episodeNo);
    try {
      const source = await apiGet<EpisodePlaySource>(`/admin/dramas/${dramaId}/episodes/${episodeNo}/play-url`);
      setActiveSource(source);
    } finally {
      setLoadingEpisodeNo(null);
    }
  }

  const activeEpisode = episodes.find((episode) => episode.episodeNo === activeSource?.episodeNo);

  return (
    <div className="episode-player">
      <div className="episode-player-main">
        {activeSource ? (
          <video
            key={activeSource.playUrl}
            className="episode-video"
            src={activeSource.playUrl}
            controls
            playsInline
            preload="metadata"
          />
        ) : (
          <div className="episode-video-placeholder">
            <PlayCircleOutlined />
            <span>选择一集播放</span>
          </div>
        )}
        <div className="episode-player-meta">
          <span>{activeEpisode ? `第 ${activeEpisode.episodeNo} 集` : '未选择剧集'}</span>
          {activeSource ? (
            <Tag color={activeSource.downloaded ? 'green' : 'blue'}>
              {activeSource.downloaded ? '本地播放' : '百度云播放'}
            </Tag>
          ) : null}
        </div>
      </div>

      <div className="episode-list-panel">
        <div className="episode-list-head">
          <span>剧集</span>
          <Tooltip title="刷新本地下载状态">
            <Button size="small" type="text" icon={<ReloadOutlined />} onClick={loadEpisodes} loading={loadingEpisodes} />
          </Tooltip>
        </div>
        <Spin spinning={loadingEpisodes}>
          {episodes.length ? (
            <div className="episode-list">
              {episodes.map((episode) => (
                <button
                  key={episode.episodeNo}
                  type="button"
                  className={episode.episodeNo === activeSource?.episodeNo ? 'episode-row episode-row-active' : 'episode-row'}
                  onClick={() => play(episode.episodeNo)}
                >
                  <span className="episode-row-title">
                    <PlayCircleOutlined />
                    <span>第 {episode.episodeNo} 集</span>
                  </span>
                  <Typography.Text className="episode-row-path" ellipsis={{ tooltip: episode.sourcePath }}>
                    {episode.title || episode.sourcePath}
                  </Typography.Text>
                  <span className="episode-row-actions">
                    <Tag color={episode.downloaded ? 'green' : 'blue'}>
                      {episode.downloaded ? '已下载' : '百度云'}
                    </Tag>
                    {episode.downloaded ? null : <CloudOutlined className="episode-cloud-icon" />}
                    <span className="episode-play-indicator">
                      {loadingEpisodeNo === episode.episodeNo ? <Spin size="small" /> : <PlayCircleOutlined />}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无剧集" />
          )}
        </Spin>
      </div>
    </div>
  );
}
