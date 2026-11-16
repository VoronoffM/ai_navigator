import { useState, type FormEvent } from 'react';
import { Check, Send } from 'lucide-react';
import type { AnalysisConfig, CheckName, Profile } from './analysis';
import type { ExtraIntegration } from './studioSettings';

export function ProviderSettings({ config, failed, provider, profile, apiKey, onProfileChange, onKeyChange, onClose }: {
  config?: AnalysisConfig;
  failed: boolean;
  provider: 'openai' | 'ollama';
  profile: Profile;
  apiKey: string;
  onProfileChange: (profile: Profile) => void;
  onKeyChange: (key: string) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState(profile);
  const [key, setKey] = useState(apiKey);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(profile.provider === provider);
  const api = provider === 'openai';

  if (!config) return <p className="studio-dialog-copy" role="status">{failed ? 'Настройки сервера недоступны.' : 'Загружаем настройки…'}</p>;
  if (api && !config.openaiModel) return <p className="studio-dialog-copy">На сервере не настроена модель OpenAI.</p>;

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      onProfileChange({ ...draft, provider: selected ? provider : api ? 'ollama' : 'openai' });
      if (api) onKeyChange(key.trim());
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
          <p>Модель OpenAI <code>{config.openaiModel}</code></p>
          <label className="studio-field">API-ключ OpenAI
            <input type="password" value={key} autoComplete="off" spellCheck={false}
              placeholder="sk-…" aria-describedby="openai-key-help" onChange={(event) => setKey(event.target.value)} />
          </label>
          <p id="openai-key-help">Ключ действует до перезагрузки страницы. При запуске материалы эпизода отправляются в OpenAI.</p>
          <div className="studio-links">
            <a href="https://platform.openai.com/api-keys" target="_blank" rel="noreferrer">Создать API-ключ</a>
            <a href="https://platform.openai.com/settings/organization/billing/overview" target="_blank" rel="noreferrer">Настроить оплату API</a>
          </div>
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
        <input type="checkbox" checked={selected} disabled={!api && !config.openaiModel} onChange={(event) => setSelected(event.target.checked)} /> Использовать для исторического разбора
      </label>
      <fieldset className="studio-assets">
        <legend>Проверки в историческом разборе</legend>
        <div className="studio-asset-options">
          {(Object.entries(config.checks) as [CheckName, string][]).map(([name, label]) => {
            const checks = draft.checks ?? config.defaults.checks;
            return (
              <label className="watch-chip" key={name}>
                <input type="checkbox" checked={checks.includes(name)} onChange={(event) =>
                  setDraft({ ...draft, checks: event.target.checked ? [...checks, name] : checks.filter((item) => item !== name) })} />
                <span className="checkbox" aria-hidden="true"><Check size={12} strokeWidth={2.5} /></span>{label}
              </label>
            );
          })}
        </div>
      </fieldset>
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
      <p>Токен используется для тестового сообщения и не сохраняется.</p>
      {connectedChat && <p className="studio-feedback" role="status">Тестовое сообщение отправлено в {connectedChat}.</p>}
      {error && <p className="studio-error" role="alert">{error}</p>}
      <div className="studio-actions">
        {connectedChat && <button className="button button-stop" type="button" disabled={pending} onClick={() => onConnect('')}>Отключить</button>}
        <button className="button button-primary" type="submit" disabled={pending}>
          <Send size={18} aria-hidden="true" /> {pending ? 'Отправляем…' : 'Отправить тест'}
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
