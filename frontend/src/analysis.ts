import { useEffect, useState } from 'react';
import type { ResearchSource, SourceAction } from './scenarios';

export type CheckName = 'news' | 'market' | 'dividends' | 'reports';
export type Profile = {
  provider?: 'ollama' | 'cloud';
  model?: string;
  apiUrl?: string;
  cloudModel?: string;
  checks?: CheckName[];
  workflow?: { actions: SourceAction[]; depth: 'brief' | 'detailed'; instructions: string; sources?: ResearchSource[] };
};
export type AnalysisConfig = {
  models: string[];
  cloud: { apiUrl: string; model: string } | null;
  checks: Record<CheckName, string>;
  defaults: { model: string; checks: CheckName[] };
};

export type InformationKind = 'fact' | 'ai_analysis' | 'opinion' | 'unverified';

export type Material = {
  id: string;
  source: string | null;
  publishedAt: string;
  title: string;
  text: string | null;
  url: string | null;
  headlineOnly: boolean;
  kind?: Exclude<InformationKind, 'ai_analysis'>;
};

export type CheckStatus = 'ok' | 'empty' | 'unavailable' | 'disabled';
type CheckResult<Facts = Record<string, never>> = {
  status: CheckStatus;
  reason: string | null;
  materials: Material[];
  facts: Facts;
};

export type Citation = Pick<Material, 'id' | 'title' | 'source' | 'url'>;
export type Statement = { text: string; citations: Citation[]; kind?: InformationKind };
type Job = { id: string; event_id: string };
export type ScenarioDelivery = { run_id: string; scenario_id: string; name: string };
type AnalysisActivity = {
  dataSource?: string;
  synthetic?: boolean;
  telegram?: 'pending' | 'sent' | 'failed' | 'unconnected';
  actions?: SourceAction[];
  requestedChecks?: CheckName[];
  completedChecks?: Partial<Record<CheckName, CheckStatus>>;
  completedActions?: SourceAction[];
  sources?: (CheckResult & { url: string; instructions: string })[];
  cbr?: CheckResult;
};
export type AnalysisResult = Job & AnalysisActivity & {
  status: 'done';
  llm: 'ready' | 'failed' | 'skipped';
  reason: string | null;
  reportFormat?: 'brief' | 'detailed';
  synthesis: {
    summary?: string | null;
    evidenceChecks?: (CheckName | 'cbr')[];
    facts: Statement[];
    hypotheses: Statement[];
    questions: string[];
  } | null;
  checks: {
    news: CheckResult;
    market: CheckResult<{ comparison?: { changePercent: number; ticker?: string } }>;
    dividends: CheckResult<{
      recommendation?: string;
      materialId?: string;
      payments?: { amount: number; currency: string; lastBuyDate: string; declaredDate: string;
        materialId: string; possibleDividendGap?: { gap: number } }[];
    }>;
    reports: CheckResult<{ calendar?: { scheduledDate: string; createdAt: string }[] }>;
  };
};

type InProgress = AnalysisActivity & { status: 'collecting' | 'analyzing' };
export type AnalysisState = AnalysisResult | InProgress | { status: 'error'; phase: InProgress['status']; reason: string };
type JobResponse = AnalysisResult | (Job & InProgress);
const storageKey = 'ai-navigator:analysis-profile';

export function readProfile(): Profile {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) ?? '{}');
    return {
      provider: saved?.provider === 'cloud' || saved?.provider === 'openai' ? 'cloud' : 'ollama',
      model: typeof saved?.model === 'string' ? saved.model : undefined,
      apiUrl: typeof saved?.apiUrl === 'string' ? saved.apiUrl : undefined,
      cloudModel: typeof saved?.cloudModel === 'string' ? saved.cloudModel : undefined,
      checks: Array.isArray(saved?.checks) ? saved.checks : undefined,
    };
  } catch {
    return {};
  }
}

export function normalizeProfile(profile: Profile, config?: AnalysisConfig): Profile {
  if (!config) return {};
  return {
    provider: profile.provider === 'cloud' && config.cloud ? 'cloud' : 'ollama',
    model: profile.model && config.models.includes(profile.model) ? profile.model : config.defaults.model,
    apiUrl: profile.apiUrl ?? config.cloud?.apiUrl,
    cloudModel: profile.cloudModel ?? config.cloud?.model,
    checks: profile.checks?.filter((name) => Object.hasOwn(config.checks, name)) ?? config.defaults.checks,
  };
}

export function saveProfile(profile: Profile) {
  localStorage.setItem(storageKey, JSON.stringify(profile));
}

export function useAnalysis(eventId: string | undefined, profile: Profile, apiKey: string,
  telegram?: ScenarioDelivery): AnalysisState | null {
  const [state, setState] = useState<{ eventId: string; profile: Profile; telegram?: ScenarioDelivery; value: AnalysisState }>();
  useEffect(() => {
    if (!eventId) return;
    const currentEventId = eventId;
    const controller = new AbortController();
    let timer: number | undefined;
    let phase: InProgress['status'] = 'collecting';
    const deliveryQuery = telegram ? '?' + new URLSearchParams({
      run_id: telegram.run_id, scenario_id: telegram.scenario_id,
    }) : '';
    let completed: AnalysisResult | undefined;

    async function request(path: string, init?: RequestInit) {
      try {
        const response = await fetch(path, { ...init, signal: controller.signal, cache: 'no-store' });
        if (!response.ok) {
          const body = await response.json().catch(() => null);
          throw new Error(typeof body?.detail === 'string' ? body.detail : 'Сервер разбора не ответил.');
        }
        const job: JobResponse = await response.json();
        if (controller.signal.aborted || job.event_id !== currentEventId) return;
        setState({ eventId: currentEventId, profile, telegram, value: job });
        if (job.status === 'done') completed = job;
        else phase = job.status;
        if (job.status !== 'done' || job.telegram === 'pending') {
          timer = window.setTimeout(() => void request(`/api/analysis/jobs/${job.id}${deliveryQuery}`), 650);
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          const reason = error instanceof Error ? error.message : 'Сервер разбора недоступен.';
          const value = completed ? { ...completed, telegram: 'failed' as const } : { status: 'error' as const, phase, reason };
          setState({ eventId: currentEventId, profile, telegram, value });
        }
      }
    }

    const cloud = profile.provider === 'cloud';
    void request(`/api/analysis/${encodeURIComponent(eventId)}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(cloud && apiKey ? { Authorization: `Bearer ${apiKey}` } : {}),
      },
      body: JSON.stringify({
        provider: profile.provider,
        checks: profile.checks,
        workflow: profile.workflow,
        telegram,
        model: cloud ? profile.cloudModel : profile.model,
        apiUrl: cloud ? profile.apiUrl : undefined,
      }),
    });
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [eventId, profile, apiKey, telegram]);

  if (!eventId) return null;
  return state?.eventId === eventId && state.profile === profile && state.telegram === telegram ? state.value
    : { status: 'collecting', actions: profile.workflow?.actions,
      requestedChecks: profile.checks };
}
