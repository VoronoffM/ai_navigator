import { useEffect, useState } from 'react';

export type CheckName = 'news' | 'market' | 'dividends' | 'reports';
export type Profile = { model?: string; checks?: CheckName[] };
export type AnalysisConfig = {
  provider: string;
  models: string[];
  checks: Record<CheckName, string>;
  defaults: Required<Profile>;
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

type CheckResult<Facts = Record<string, never>> = {
  status: 'ok' | 'empty' | 'unavailable' | 'disabled';
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

export type AnalysisState = AnalysisResult | { status: 'collecting' } | { status: 'analyzing' } | { status: 'error'; reason: string };
type JobResponse = AnalysisResult | (Job & { status: 'collecting' | 'analyzing' });
const storageKey = 'ai-navigator:analysis-profile';

export function readProfile(): Profile {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) ?? '{}');
    return {
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
    model: profile.model && config.models.includes(profile.model) ? profile.model : config.defaults.model,
    checks: profile.checks?.filter((name) => Object.hasOwn(config.checks, name)) ?? config.defaults.checks,
  };
}

export function saveProfile(profile: Profile) {
  localStorage.setItem(storageKey, JSON.stringify(profile));
}

export function useAnalysis(eventId: string | undefined, profile: Profile): AnalysisState | null {
  const [state, setState] = useState<{ eventId: string; profile: Profile; value: AnalysisState }>();
  useEffect(() => {
    if (!eventId) return;
    const currentEventId = eventId;
    const controller = new AbortController();
    let timer: number | undefined;

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
          timer = window.setTimeout(() => void request(`/api/analysis/jobs/${job.id}`), 650);
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          const reason = error instanceof Error ? error.message : 'Сервер разбора недоступен.';
          setState({ eventId: currentEventId, profile, value: { status: 'error', reason } });
        }
      }
    }

    void request(`/api/analysis/${encodeURIComponent(eventId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(profile),
    });
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [eventId, profile]);

  if (!eventId) return null;
  return state?.eventId === eventId && state.profile === profile ? state.value : { status: 'collecting' };
}
