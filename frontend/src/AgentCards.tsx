import type { MouseEvent } from 'react';
import { BackgroundBeams } from './BackgroundBeams';
import { agentPalette } from './studioSettings';

type Card = { id: string; name: string; activeScenarioCount: number };
type CardClick = (event: MouseEvent<HTMLButtonElement>) => void;

const scenarioPlural = new Intl.PluralRules('ru');

function usageStatus(count: number) {
  if (count === 0) return 'Не используется';
  const noun = scenarioPlural.select(count) === 'one' ? 'сценарии' : 'сценариях';
  return `Используется в ${count} ${noun}`;
}

export function AgentCards({ cards, onOpen, onAdd }: {
  cards: Card[];
  onOpen: (id: string, event: MouseEvent<HTMLButtonElement>) => void;
  onAdd: CardClick;
}) {
  return (
    <section aria-labelledby="agents-title">
      <div className="studio-section-header studio-agents-header">
        <h2 id="agents-title">Агенты</h2>
      </div>
      <div className="studio-agents">
        <BackgroundBeams />
        {cards.length > 0 && (
          <div className="studio-agent-list">
            {cards.map((card, index) => (
              <div className="studio-agent-slot" key={card.id}>
                <button className="studio-card studio-agent" type="button" aria-haspopup="dialog"
                  onClick={(event) => onOpen(card.id, event)}>
                  <span className="studio-agent-art agent-gradient" data-palette={agentPalette(index)}>
                    <span className="studio-agent-copy">
                      <span className="studio-status" data-active={card.activeScenarioCount > 0}>
                        {usageStatus(card.activeScenarioCount)}
                      </span>
                      <span className="studio-card-title studio-agent-name" title={card.name}>
                        {card.name}
                      </span>
                    </span>
                  </span>
                </button>
              </div>
            ))}
          </div>
        )}
        <button className="studio-card studio-add-agent" type="button" aria-haspopup="dialog" onClick={onAdd}>
          <svg className="studio-add-agent-art" width="80" height="88" viewBox="0 0 80 88" fill="none" aria-hidden="true">
            <g className="studio-add-agent-back">
              <rect x="17" y="12" width="51" height="65" rx="9" fill="#DCE2EB" stroke="#BAC3D1" strokeWidth="1.5" transform="rotate(11 42.5 44.5)" />
            </g>
            <g className="studio-add-agent-front">
              <rect x="14" y="11" width="51" height="65" rx="9" fill="#F5F6F8" stroke="#BAC3D1" strokeWidth="1.5" transform="rotate(-9 39.5 43.5)" />
              <g className="studio-add-agent-plus">
                <circle cx="40" cy="41" r="17" fill="#FFDD2D" />
                <path d="M40 32V50M31 41H49" stroke="#292718" strokeWidth="2.5" strokeLinecap="round" />
              </g>
            </g>
          </svg>
          <span className="studio-card-title">Добавить<br />агента</span>
        </button>
      </div>
    </section>
  );
}
