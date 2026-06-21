import { useEffect, useMemo, useState } from 'react';

type Platform = 'MAC' | 'WINDOWS';

type ApiResponse<T> = {
  success: boolean;
  data: T;
  error?: { message: string } | null;
};

type PublicVersion = {
  available: boolean;
  platform: Platform;
  version?: string;
  releaseNotes?: string;
  mandatory: boolean;
  fileName?: string;
  fileSize: number;
};

type DownloadAccess = PublicVersion & {
  valid: boolean;
  downloadUrl: string;
};

const apiBase = import.meta.env.VITE_API_BASE || '/api';

const posters = [
  'https://images.unsplash.com/photo-1485846234645-a62644f84728?auto=format&fit=crop&w=640&q=80',
  'https://images.unsplash.com/photo-1505686994434-e3cc5abf1330?auto=format&fit=crop&w=640&q=80',
  'https://images.unsplash.com/photo-1517604931442-7e0c8ed2963c?auto=format&fit=crop&w=640&q=80',
];

function detectPlatform(): Platform {
  const ua = navigator.userAgent.toLowerCase();
  return ua.includes('win') ? 'WINDOWS' : 'MAC';
}

function formatSize(size: number) {
  if (!size) return '';
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBase}${path}`);
  const body = await response.json() as ApiResponse<T>;
  if (!response.ok || !body.success) {
    throw new Error(body.error?.message || '请求失败');
  }
  return body.data;
}

async function apiPost<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const body = await response.json() as ApiResponse<T>;
  if (!response.ok || !body.success) {
    throw new Error(body.error?.message || '请求失败');
  }
  return body.data;
}

function resolveDownloadUrl(url: string) {
  if (/^https?:\/\//.test(url)) return url;
  const origin = apiBase.startsWith('http') ? new URL(apiBase).origin : window.location.origin;
  return new URL(url, origin).toString();
}

export function App() {
  const [platform, setPlatform] = useState<Platform>(() => detectPlatform());
  const [version, setVersion] = useState<PublicVersion | null>(null);
  const [inviteCode, setInviteCode] = useState('');
  const [downloadUrl, setDownloadUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [checking, setChecking] = useState(false);
  const [message, setMessage] = useState('');

  const platformName = platform === 'MAC' ? 'macOS' : 'Windows';
  const versionMeta = useMemo(() => {
    if (!version?.available) return '暂无可下载版本';
    return [version.version, version.fileName, formatSize(version.fileSize)].filter(Boolean).join(' · ');
  }, [version]);

  useEffect(() => {
    let ignore = false;
    setLoading(true);
    setMessage('');
    setDownloadUrl('');
    apiGet<PublicVersion>(`/public/desktop-versions/latest?platform=${platform}`)
      .then((data) => {
        if (!ignore) setVersion(data);
      })
      .catch((error: Error) => {
        if (!ignore) {
          setVersion(null);
          setMessage(error.message);
        }
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });
    return () => {
      ignore = true;
    };
  }, [platform]);

  async function validateInvite() {
    if (!inviteCode.trim()) {
      setMessage('请输入邀请码');
      return;
    }
    setChecking(true);
    setMessage('');
    setDownloadUrl('');
    try {
      const access = await apiPost<DownloadAccess>('/public/download-invites/validate', {
        code: inviteCode,
        platform,
      });
      const url = resolveDownloadUrl(access.downloadUrl);
      setDownloadUrl(url);
      setMessage('验证通过，下载已准备好');
      window.location.href = url;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '邀请码验证失败');
    } finally {
      setChecking(false);
    }
  }

  return (
    <main className="shell">
      <section className="poster-wall" aria-label="短剧内容">
        {posters.map((poster, index) => (
          <img key={poster} src={poster} alt="" className={`poster poster-${index + 1}`} />
        ))}
      </section>

      <section className="download-panel">
        <div className="brand-row">
          <div className="brand-mark">
            <img src="/app-icon.svg" alt="AI Drama Desktop" />
          </div>
          <div>
            <p className="eyebrow">AI Drama Desktop</p>
            <h1>短剧分发工具</h1>
          </div>
        </div>

        <div className="platform-switch" role="tablist" aria-label="选择系统">
          <button className={platform === 'MAC' ? 'active' : ''} onClick={() => setPlatform('MAC')}>macOS</button>
          <button className={platform === 'WINDOWS' ? 'active' : ''} onClick={() => setPlatform('WINDOWS')}>Windows</button>
        </div>

        <div className="version-card">
          <span>{loading ? '正在获取最新版' : platformName}</span>
          <strong>{versionMeta}</strong>
        </div>

        <label className="invite-field">
          <span>邀请码</span>
          <input
            value={inviteCode}
            onChange={(event) => setInviteCode(event.target.value.toUpperCase())}
            placeholder="请输入邀请码"
            autoComplete="one-time-code"
          />
        </label>

        <button className="download-button" disabled={checking || loading || !version?.available} onClick={validateInvite}>
          {checking ? '验证中...' : `获取 ${platformName} 安装包`}
        </button>

        {downloadUrl ? (
          <a className="secondary-link" href={downloadUrl}>如果没有自动开始，请点击这里下载</a>
        ) : null}
        {message ? <p className="message">{message}</p> : null}
      </section>
    </main>
  );
}
