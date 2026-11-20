import { useState, type FormEvent } from 'react';
import { CalendarDays, CandlestickChart, ExternalLink, History, Newspaper, Percent, Send } from 'lucide-react';
import type { AnalysisConfig, CheckName, Profile } from './analysis';
import { defaultScenarioChecks, scenarioChecks } from './scenarios';
import type { ExtraIntegration } from './studioSettings';
import { SourceInfo } from './SourceInfo';

const investTools = {
  news: {
    icon: Newspaper,
    name: 'invest_get_news',
    description: 'Ищет публикации по бумаге, вышедшие к моменту сигнала.',
  },
  market: {
    icon: CandlestickChart,
    name: 'invest_get_candles',
    description: 'Загружает свечи за нужный период. Агент сравнивает движение бумаги с индексом IMOEX.',
  },
  dividends: {
    icon: Percent,
    name: 'invest_get_share_dividends',
    description: 'Проверяет, есть ли рядом с сигналом записи о дивидендах, и показывает суммы и ключевые даты.',
  },
  reports: {
    icon: CalendarDays,
    name: 'invest_get_instrument_reports',
    description: 'Проверяет по календарю, был ли на день сигнала запланирован выход отчётности.',
  },
} satisfies Record<CheckName, { icon: typeof Newspaper; name: string; description: string }>;

export function InvestMcpDetails() {
  return (
    <div className="studio-mcp">
      <p className="studio-dialog-copy">Данные, доступные агентам для анализа сигналов</p>
      <ul className="studio-mcp-tools" role="list">
        {defaultScenarioChecks.map((check) => {
          const { icon: Icon } = investTools[check];
          return (
            <li key={check}>
              <span className="studio-icon"><Icon size={18} aria-hidden="true" /></span>
              <span className="studio-mcp-tool-name">{check === 'market' ? 'Свечи и индекс MOEX' : scenarioChecks[check]}</span>
            </li>
          );
        })}
      </ul>
      <div className="studio-mcp-demo">
        <History size={18} aria-hidden="true" />
        <div>
          <h3>Демо-режим</h3>
          <p>Используются сохранённые данные</p>
        </div>
        <SourceInfo label="О демо-режиме" text="Разбор воспроизводит сохранённые исторические эпизоды по разным компаниям. В дальнейшем агент будет запрашивать данные через T-Invest MCP." />
      </div>
      <a className="studio-mcp-docs" href="https://developer.tbank.ru/invest/mcp" target="_blank" rel="noreferrer">
        Документация <ExternalLink size={13} aria-hidden="true" />
      </a>
    </div>
  );
}

export function ProviderSettings({ config, failed, provider, profile, apiKey, onProfileChange, onKeyChange, onClose }: {
  config?: AnalysisConfig;
  failed: boolean;
  provider: 'cloud' | 'ollama';
  profile: Profile;
  apiKey: string;
  onProfileChange: (profile: Profile) => void;
  onKeyChange: (key: string) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState(profile);
  const [key, setKey] = useState(apiKey);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(true);
  const api = provider === 'cloud';

  if (!config) return <p className="studio-dialog-copy" role="status">{failed ? 'Настройки сервера недоступны.' : 'Загружаем настройки…'}</p>;
  if (api && !config.cloud) return <p className="studio-dialog-copy">LLM API недоступен на сервере.</p>;

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const apiUrl = draft.apiUrl?.trim();
    const cloudModel = draft.cloudModel?.trim();
    const trimmedKey = key.trim();
    if (api) {
      const url = apiUrl && URL.canParse(apiUrl) ? new URL(apiUrl) : null;
      if (!url || url.protocol !== 'https:' || url.username || url.password || url.search || url.hash) {
        setError('Укажите публичный HTTPS-адрес API без логина, параметров и фрагмента.');
        return;
      }
      if (!cloudModel) {
        setError('Укажите идентификатор модели.');
        return;
      }
      if (trimmedKey && !/^[!-~]+$/.test(trimmedKey)) {
        setError('Проверьте формат API-ключа.');
        return;
      }
    }
    try {
      onProfileChange({ ...draft, apiUrl, cloudModel, localConfigured: api ? draft.localConfigured : selected, provider: selected ? provider : api ? 'ollama' : 'cloud' });
      if (api) onKeyChange(trimmedKey);
      onClose();
    } catch {
      setError('Не удалось сохранить профиль в браузере.');
    }
  }

  return (
    <form className="studio-form" onSubmit={save}>
      <p>Эти настройки применяются при запуске исторического эпизода в Market.</p>
      {api ? (
        <>
          <label className="studio-field">Адрес API
            <input type="url" required maxLength={2048} value={draft.apiUrl ?? ''} autoComplete="off" spellCheck={false}
              placeholder="https://api.example.com/v1" aria-describedby="cloud-url-help" onChange={(event) => {
                setDraft({ ...draft, apiUrl: event.target.value });
                setKey('');
              }} />
          </label>
          <p id="cloud-url-help">Укажите базовый URL или полный адрес совместимого эндпоинта Chat Completions.</p>
          <label className="studio-field">Идентификатор модели
            <input required maxLength={150} value={draft.cloudModel ?? ''} autoComplete="off" spellCheck={false}
              onChange={(event) => setDraft({ ...draft, cloudModel: event.target.value })} />
          </label>
          <label className="studio-field">API-ключ
            <input type="password" required={selected} value={key} autoComplete="off" spellCheck={false}
              aria-describedby="cloud-key-help" onChange={(event) => setKey(event.target.value)} />
          </label>
          <p id="cloud-key-help">Ключ действует до перезагрузки страницы. Материалы эпизода отправляются выбранному провайдеру.</p>
        </>
      ) : (
        <>
          <label className="studio-field">Локальная модель Ollama
            <select value={draft.model ?? config.defaults.model} onChange={(event) => setDraft({ ...draft, model: event.target.value })}>
              {config.models.map((model) => <option key={model} value={model}>{model}</option>)}
            </select>
          </label>
          <details>
            <summary>Как запустить Ollama</summary>
            <ol className="studio-setup-steps">
              <li><a href="https://ollama.com/download" target="_blank" rel="noreferrer">Установите Ollama</a> на компьютер, где запущен AI Штурман.</li>
              <li>Откройте приложение Ollama или запустите <code>ollama serve</code> в терминале.</li>
              <li>Загрузите выбранную модель командой <code>ollama pull {draft.model ?? config.defaults.model}</code>.</li>
            </ol>
          </details>
        </>
      )}
      <label className="studio-check">
        <input type="checkbox" checked={selected} disabled={!api && selected && (!config.cloud || !apiKey)}
          onChange={(event) => setSelected(event.target.checked)} /> Использовать для исторического разбора
      </label>
      {error && <p className="studio-error" role="alert">{error}</p>}
      <div className="studio-actions">
        <button className="button button-stop" type="button" onClick={onClose}>Отмена</button>
        <button className="button button-primary" type="submit">Сохранить настройки</button>
      </div>
    </form>
  );
}

export function TelegramSettings({ connectedChat, onConnect }: { connectedChat: string; onConnect: (chat: string) => void }) {
  const [token, setToken] = useState('');
  const [chat, setChat] = useState(connectedChat);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');

  async function test(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError('');
    try {
      const response = await fetch('/api/studio/telegram/test', {
        method: 'POST',
        signal: AbortSignal.timeout(12000),
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: token.trim(), chat_id: chat.trim() }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(typeof payload?.detail === 'string' ? payload.detail : 'Проверьте формат токена и ID чата.');
      }
      onConnect(chat.trim());
      setToken('');
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : 'Не удалось проверить подключение.');
    } finally {
      setPending(false);
    }
  }

  async function disconnect() {
    setPending(true);
    setError('');
    try {
      const response = await fetch('/api/studio/telegram', { method: 'DELETE', signal: AbortSignal.timeout(12000) });
      if (!response.ok) throw new Error();
      onConnect('');
      setToken('');
    } catch {
      setError('Не удалось отключить Telegram. Повторите попытку.');
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="studio-form" onSubmit={test}>
      <p>Создайте бота через <a href="https://t.me/BotFather" target="_blank" rel="noreferrer">BotFather</a> и откройте с ним чат или добавьте его в нужную группу.</p>
      <label className="studio-field">Токен бота
        <input type="password" required value={token} autoComplete="off" spellCheck={false} placeholder="Токен из BotFather"
          disabled={pending} onChange={(event) => setToken(event.target.value)} />
      </label>
      <label className="studio-field">ID чата
        <input required value={chat} autoComplete="off" spellCheck={false} placeholder="Например, 123456789"
          pattern="-?[0-9]+|@[a-zA-Z0-9_]+" maxLength={80} disabled={pending} onChange={(event) => setChat(event.target.value)} />
      </label>
      <p>После успешного теста токен хранится в памяти сервера до отключения или перезапуска. В сценарии выберите Telegram в поле «Уведомления».</p>
      {connectedChat && <p className="studio-feedback" role="status">Подключён чат {connectedChat}.</p>}
      {error && <p className="studio-error" role="alert">{error}</p>}
      <div className="studio-actions">
        {connectedChat && <button className="button button-stop" type="button" disabled={pending} onClick={() => void disconnect()}>Отключить</button>}
        <button className="button button-primary" type="submit" disabled={pending}>
          <Send size={18} aria-hidden="true" /> {pending ? 'Подождите…' : 'Отправить тест'}
        </button>
      </div>
    </form>
  );
}

export function ExtraSettings({ integration, onSave, onCancel, onRemove }: {
  integration?: ExtraIntegration;
  onSave: (item: ExtraIntegration, editing: boolean) => void;
  onCancel: () => void;
  onRemove: () => void;
}) {
  const [error, setError] = useState('');

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const name = String(data.get('name')).trim();
    const endpoint = String(data.get('endpoint')).trim();
    try {
      const url = new URL(endpoint);
      if (url.protocol !== 'https:' || url.username || url.password) throw new Error('Invalid HTTPS address');
    } catch {
      setError('Введите HTTPS-адрес без логина и пароля.');
      return;
    }
    onSave({ id: integration?.id ?? crypto.randomUUID(), name, endpoint }, Boolean(integration));
  }

  return (
    <form className="studio-form" onSubmit={save}>
      <p>Сохраните адрес сервиса для будущего подключения. Черновик хранится в этом браузере.</p>
      <label className="studio-field">Название
        <input name="name" required pattern=".*\S.*" maxLength={60} defaultValue={integration?.name} placeholder="Например, командный вебхук" />
      </label>
      <label className="studio-field">Адрес сервиса
        <input name="endpoint" type="url" required maxLength={500} defaultValue={integration?.endpoint} placeholder="https://…" />
      </label>
      {error && <p className="studio-error" role="alert">{error}</p>}
      <div className="studio-actions">
        <button className="button button-stop" type="button" onClick={integration ? onRemove : onCancel}>{integration ? 'Удалить' : 'Отмена'}</button>
        <button className="button button-primary" type="submit">Сохранить черновик</button>
      </div>
    </form>
  );
}

export type MailConfig = {
  host: string; port: number; security: 'ssl' | 'starttls'; username: string; sender: string; recipient: string;
};

export function MailSettings({ connected, onConnect }: {
  connected: MailConfig | null; onConnect: (settings: MailConfig | null) => void;
}) {
  const [settings, setSettings] = useState<MailConfig>(connected ?? {
    host: '', port: 465, security: 'ssl', username: '', sender: '', recipient: '',
  });
  const [password, setPassword] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [tested, setTested] = useState(false);
  function update(patch: Partial<MailConfig>) { setSettings((current) => ({ ...current, ...patch })); setTested(false); }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true); setError(''); setTested(false);
    const normalized = { ...settings, host: settings.host.trim(), username: settings.username.trim(),
      sender: settings.sender.trim(), recipient: settings.recipient.trim() };
    try {
      const response = await fetch('/api/studio/mail/test', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...normalized, password }), signal: AbortSignal.timeout(60000),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(typeof payload?.detail === 'string' ? payload.detail : 'Проверьте параметры почты.');
      }
      onConnect(normalized); setPassword(''); setTested(true);
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : 'Не удалось подключить почту.');
    } finally { setPending(false); }
  }
  async function disconnect() {
    setPending(true); setError('');
    try {
      const response = await fetch('/api/studio/mail', { method: 'DELETE', signal: AbortSignal.timeout(12000) });
      if (!response.ok) throw new Error();
      onConnect(null); setPassword(''); setTested(false);
    } catch { setError('Не удалось отключить почту. Повторите попытку.'); }
    finally { setPending(false); }
  }
  return <form className="studio-form" onSubmit={submit}>
    <p>Укажите параметры SMTP из настроек вашего почтового сервиса. Для входа используйте пароль приложения.</p>
    <label className="studio-field">SMTP-сервер
      <input required value={settings.host} maxLength={253} placeholder="smtp.example.ru" disabled={pending}
        autoComplete="off" spellCheck={false} onChange={(e) => update({ host: e.target.value })} />
    </label>
    <label className="studio-field">Защита соединения
      <select value={settings.security} disabled={pending} onChange={(e) => {
        const security = e.target.value as MailConfig['security']; update({ security, port: security === 'ssl' ? 465 : 587 });
      }}><option value="ssl">SSL/TLS</option><option value="starttls">STARTTLS</option></select>
    </label>
    <label className="studio-field">Порт
      <input type="number" required min={1} max={65535} value={settings.port} disabled={pending}
        onChange={(e) => update({ port: Number(e.target.value) })} />
    </label>
    <label className="studio-field">Логин SMTP
      <input required value={settings.username} maxLength={254} placeholder="user@example.ru" disabled={pending}
        autoComplete="off" onChange={(e) => update({ username: e.target.value })} />
    </label>
    <label className="studio-field">Пароль приложения
      <input type="password" required value={password} maxLength={1024} autoComplete="new-password" disabled={pending}
        onChange={(e) => { setPassword(e.target.value); setTested(false); }} />
    </label>
    <label className="studio-field">Почта отправителя
      <input type="email" required value={settings.sender} maxLength={254} placeholder="user@example.ru" disabled={pending}
        onChange={(e) => update({ sender: e.target.value })} />
    </label>
    <label className="studio-field">Почта для отчётов
      <input type="email" required value={settings.recipient} maxLength={254} placeholder="reports@example.ru" disabled={pending}
        onChange={(e) => update({ recipient: e.target.value })} />
    </label>
    <p>Кнопка отправит тестовое письмо и сохранит подключение после успешной отправки. Затем выберите «Почта» в действии «Отправка отчета». Настройки хранятся в памяти сервера до отключения или перезапуска.</p>
    {connected && <p className="studio-feedback" role="status">Подключена почта {connected.recipient}.</p>}
    {tested && <p className="studio-feedback" role="status">Сервер принял тестовое письмо. Проверьте входящие и папку «Спам».</p>}
    {error && <p className="studio-error" role="alert">{error}</p>}
    <div className="studio-actions">
      {connected && <button className="button button-stop" type="button" disabled={pending} onClick={() => void disconnect()}>Отключить</button>}
      <button className="button button-primary" type="submit" disabled={pending}>{pending ? 'Отправляем…' : 'Отправить тест и подключить'}</button>
    </div>
  </form>;
}
