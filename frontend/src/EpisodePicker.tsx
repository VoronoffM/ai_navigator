import { Pause, Play, SkipForward } from 'lucide-react';
import { SpringDropdown } from './SpringDropdown';
import type { EpisodeMetadata } from './replay';

export function EpisodePicker({ episodes, selected, metadata, compatibleCount, historical, paused, finished,
  progress, total, speed, issue, onSelect, onStudio, onPause, onStep, onSpeed, onRetry }: {
  episodes: EpisodeMetadata[]; selected: string; metadata?: EpisodeMetadata; compatibleCount: number;
  historical: boolean; paused: boolean; finished: boolean; progress: number; total: number; speed: string;
  issue: string | null; onSelect: (id: string) => void; onStudio: () => void;
  onPause: () => void; onStep: () => void; onSpeed: (speed: string) => void; onRetry: () => void;
}) {
  const options = episodes.map((episode) => ({ value: episode.id, label: episode.title }));
  return <section className="episode-picker" aria-labelledby="episode-picker-title">
    <div className="episode-picker-heading">
      <h3 id="episode-picker-title">Эпизод для воспроизведения</h3>
      {metadata && <span className="episode-kind" data-synthetic={metadata.kind === 'synthetic'}>
        {metadata.kind === 'synthetic' ? 'Симуляция' : 'История'}
      </span>}
    </div>
    {options.length > 0 ? <SpringDropdown floating label="Эпизод для воспроизведения" options={options}
      value={selected} onChange={onSelect} /> : <p role="status">{issue ?? 'Загружаем эпизоды…'}</p>}
    {issue && <p role="alert">{issue} <button type="button" className="episode-link" onClick={onRetry}>Повторить загрузку</button></p>}
    {metadata && <>
      <p className="episode-description">{metadata.description}</p>
      <p className="episode-origin">{metadata.date} · {metadata.source}</p>
      <details className="episode-note"><summary>О данных эпизода</summary><p>{metadata.note}</p></details>
      <div className="episode-compatibility" role="status">
        {compatibleCount > 0 ? <span>Подходящих правил: {compatibleCount}</span>
          : <span>Для {metadata.ticker} нет подходящего активного правила на 1 час.</span>}
        <button type="button" className="episode-link" onClick={onStudio}>Правила в Agent Studio</button>
      </div>
      {metadata.ticker === 'BELU' && <p className="episode-hint">Для первого разрыва между сессиями подойдёт правило «Изменение цены по фиксированному порогу». Часовая Z-оценка для этого разрыва недоступна.</p>}
    </>}
    {historical && <div className="episode-playback">
      <div className="episode-progress" role="status">
        <span>{finished ? 'Эпизод завершён' : paused ? 'На паузе' : 'Воспроизведение'}</span>
        <span className="figures">{progress} / {total}</span>
      </div>
      <progress aria-label="Прогресс эпизода" max={Math.max(1, total)} value={progress} />
      <div className="episode-playback-actions">
        <button type="button" className="episode-transport" disabled={finished} onClick={onPause}>
          {paused ? <Play size={14} aria-hidden="true" /> : <Pause size={14} aria-hidden="true" />}
          {paused ? 'Продолжить' : 'Пауза'}
        </button>
        <button type="button" className="episode-transport" disabled={finished} onClick={onStep}>
          <SkipForward size={14} aria-hidden="true" /> Шаг
        </button>
        <label className="episode-speed">Скорость
          <select aria-label="Скорость воспроизведения" value={speed} onChange={(event) => onSpeed(event.target.value)}>
            <option value="1">1×</option><option value="2">2×</option><option value="4">4×</option>
          </select>
        </label>
      </div>
    </div>}
  </section>;
}
