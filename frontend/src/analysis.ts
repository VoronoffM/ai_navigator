import { useEffect, useState } from 'react';

export type CheckName = 'news' | 'market' | 'dividends' | 'reports';
export type Profile = { provider?: 'ollama' | 'openai'; model?: string; checks?: CheckName[] };
export type AnalysisConfig = {
  models: string[];
  openaiModel: string | null;
  checks: Record<CheckName, string>;
  defaults: { model: string; checks: CheckName[] };
};

type Material = {
  id: string;
  source: string | null;
  publishedAt: string;
  title: string;
  text: string | null;
  url: string | null;
  headlineOnly: boolean;
};

export type CheckStatus = 'ok' | 'empty' | 'unavailable' | 'disabled';
type CheckResult<Facts = Record<string, never>> = {
  status: CheckStatus;
  reason: string | null;
  materials: Material[];
  facts: Facts;
};

type Citation = Pick<Material, 'id' | 'title' | 'source' | 'url'>;
export type Statement = { text: string; citations: Citation[] };
type Job = { id: string; event_id: string };
export type AnalysisResult = Job & {
  status: 'done';
  llm: 'ready' | 'failed' | 'skipped';
  reason: string | null;
  synthesis: { facts: Statement[]; hypotheses: Statement[]; questions: string[] } | null;
  checks: {
    news: CheckResult;
    market: CheckResult<{ comparison?: { changePercent: number } }>;
    dividends: CheckResult<{
      recommendation?: string;
      materialId?: string;
      payments?: { amount: number; currency: string; lastBuyDate: string; declaredDate: string;
        materialId: string; possibleDividendGap?: { gap: number } }[];
    }>;
    reports: CheckResult<{ calendar?: { scheduledDate: string; createdAt: string }[] }>;
  };
};

type Collection = { status: 'collecting'; completedChecks?: Partial<Record<CheckName, CheckStatus>> };
type InProgress = Collection | { status: 'analyzing' };
export type AnalysisState = AnalysisResult | InProgress | { status: 'error'; phase: InProgress['status']; reason: string };
type JobResponse = AnalysisResult | (Job & InProgress);
const storageKey = 'ai-navigator:analysis-profile';

export function readProfile(): Profile {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) ?? '{}');
    return {
      provider: saved?.provider === 'openai' ? 'openai' : 'ollama',
      model: typeof saved?.model === 'string' ? saved.model : undefined,
      checks: Array.isArray(saved?.checks) ? saved.checks : undefined,
    };
  } catch {
    return {};
  }
}

export function normalizeProfile(profile: Profile, config?: AnalysisConfig): Profile {
  if (!config) return {};
  return {
    provider: profile.provider === 'openai' && config.openaiModel ? 'openai' : 'ollama',
    model: profile.model && config.models.includes(profile.model) ? profile.model : config.defaults.model,
    checks: profile.checks?.filter((name) => Object.hasOwn(config.checks, name)) ?? config.defaults.checks,
  };
}

export function saveProfile(profile: Profile) {
  localStorage.setItem(storageKey, JSON.stringify(profile));
}

export function useAnalysis(eventId: string | undefined, profile: Profile, openaiKey: string): AnalysisState | null {
  const [state, setState] = useState<{ eventId: string; profile: Profile; value: AnalysisState }>();
  useEffect(() => {
    if (!eventId) return;
    const currentEventId = eventId;
    const controller = new AbortController();
    let timer: number | undefined;
    let phase: InProgress['status'] = 'collecting';

    async function request(path: string, init?: RequestInit) {
      try {
        const response = await fetch(path, { ...init, signal: controller.signal, cache: 'no-store' });
        if (!response.ok) {
          const body = await response.json().catch(() => null);
          throw new Error(typeof body?.detail === 'string' ? body.detail : 'Сервер разбора не ответил.');
        }
        const job: JobResponse = await response.json();
        if (controller.signal.aborted || job.event_id !== currentEventId) return;
        setState({ eventId: currentEventId, profile, value: job });
        if (job.status === 'collecting' || job.status === 'analyzing') {
          phase = job.status;
          timer = window.setTimeout(() => void request(`/api/analysis/jobs/${job.id}`), 650);
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          const reason = error instanceof Error ? error.message : 'Сервер разбора недоступен.';
          setState({ eventId: currentEventId, profile, value: { status: 'error', phase, reason } });
        }
      }
    }

    void request(`/api/analysis/${encodeURIComponent(eventId)}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(profile.provider === 'openai' && openaiKey ? { Authorization: `Bearer ${openaiKey}` } : {}),
      },
      body: JSON.stringify(profile.provider === 'openai' ? { ...profile, model: undefined } : profile),
    });
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [eventId, profile, openaiKey]);

  if (!eventId) return null;
  return state?.eventId === eventId && state.profile === profile ? state.value : { status: 'collecting' };
}
