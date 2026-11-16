import type { MouseEvent } from 'react';
import { Plus } from 'lucide-react';

type Card = { id: string; name: string; activeScenarioCount: number };
type CardClick = (event: MouseEvent<HTMLButtonElement>) => void;

const palettes = ['amber', 'orchid', 'peach'] as const;
const scenarioPlural = new Intl.PluralRules('ru');

function usageStatus(count: number) {
  if (count === 0) return 'Не используется';
  const noun = scenarioPlural.select(count) === 'one' ? 'сценарии' : 'сценариях';
  return `Используется в ${count} ${noun}`;
}

function nameLines(name: string) {
  const words = name.trim().split(/\s+/);
  const middle = Math.ceil(words.length / 2);
  return [words.slice(0, middle).join(' '), words.slice(middle).join(' ')];
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
        {cards.length > 0 && (
          <div className="studio-agent-list">
            {cards.map((card, index) => (
              <div className="studio-agent-slot" key={card.id}>
                <button className="studio-card studio-agent" type="button" aria-haspopup="dialog"
                  onClick={(event) => onOpen(card.id, event)}>
                  <span className="studio-agent-art" data-palette={palettes[index % palettes.length]}>
                    <span className="studio-agent-copy">
                      <span className="studio-status" data-active={card.activeScenarioCount > 0}>
                        {usageStatus(card.activeScenarioCount)}
                      </span>
                      <span className="studio-card-title studio-agent-name" title={card.name}>
                        {nameLines(card.name).map((line, index) => <span key={index}>{line}</span>)}
                      </span>
                    </span>
                  </span>
                </button>
              </div>
            ))}
          </div>
        )}
        <button className="studio-card studio-add-agent" type="button" aria-haspopup="dialog" onClick={onAdd}>
          <Plus size={34} strokeWidth={1.5} aria-hidden="true" />
          <span className="studio-card-title">Добавить агента</span>
        </button>
      </div>
    </section>
  );
}
