'use client';

import { useEffect, useState } from 'react';
import { Activity, Clock, Filter, AlertTriangle } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';

interface EvalMetric {
  faithfulness: number;
  relevance: number;
  precision: number;
  recall: number;
}

interface EvaluationEvent {
  run_id: string;
  pipeline_id: string;
  query: string;
  overall_score: number;
  metrics: EvalMetric;
  timestamp: string;
}

export default function EvaluationsPage() {
  const [events, setEvents] = useState<EvaluationEvent[]>([]);
  const [status, setStatus] = useState<'connecting' | 'connected' | 'error'>('connecting');
  const [minScoreFilter, setMinScoreFilter] = useState<number>(0);

  // Helper to fetch pipeline names since the event only has pipeline_id
  const { data: pipelines = [] } = useQuery({
    queryKey: ['pipelines'],
    queryFn: async () => {
      const res = await api.get('/pipelines');
      return res.data;
    }
  });

  const getPipelineName = (id: string) => {
    const p = pipelines.find((p: any) => p.id === id);
    return p ? p.name : 'Unknown Pipeline';
  };

  useEffect(() => {
    const eventSource = new EventSource('http://localhost:8000/evaluations/stream');

    eventSource.onopen = () => setStatus('connected');
    
    eventSource.onmessage = (event) => {
      try {
        const newEval = JSON.parse(event.data);
        newEval.timestamp = new Date().toISOString(); // Attach local receive time
        setEvents((prev) => [newEval, ...prev]); // Prepend new events
      } catch (err) {
        console.error("Failed to parse evaluation event", err);
      }
    };

    eventSource.onerror = () => {
      setStatus('error');
      eventSource.close();
    };

    return () => eventSource.close();
  }, []);

  const filteredEvents = events.filter(e => e.overall_score >= minScoreFilter);

  const getScoreColor = (score: number) => {
    if (score > 0.8) return 'text-status-success';
    if (score >= 0.6) return 'text-status-warning';
    return 'text-status-danger';
  };

  const MetricBar = ({ label, score }: { label: string, score: number }) => (
    <div className="flex items-center justify-between text-xs">
      <span className="text-content-secondary w-20">{label}</span>
      <div className="flex-1 mx-3 h-1.5 bg-surface-secondary rounded-full overflow-hidden">
        <div 
          className="h-full bg-accent-secondary rounded-full" 
          style={{ width: `${Math.max(0, Math.min(100, score * 100))}%` }} 
        />
      </div>
      <span className="font-mono text-content-primary w-8 text-right">{(score * 100).toFixed(0)}</span>
    </div>
  );

  return (
    <div className="w-full h-full flex flex-col space-y-6">
      
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-semibold text-content-primary tracking-tight">Live Evaluation Feed</h1>
          <p className="text-content-secondary mt-1 text-sm">Real-time telemetry of automated LLM-as-a-Judge audits.</p>
        </div>
        
        {/* Status Badge */}
        <div className={`flex items-center px-3 py-1.5 rounded-lg border text-xs font-medium ${
          status === 'connected' ? 'bg-status-success/10 border-status-success/30 text-status-success' : 
          status === 'error' ? 'bg-status-danger/10 border-status-danger/30 text-status-danger' : 
          'bg-status-warning/10 border-status-warning/30 text-status-warning'
        }`}>
          {status === 'connected' ? (
            <><div className="w-2 h-2 rounded-full bg-status-success animate-pulse mr-2" /> Live Connection</>
          ) : status === 'error' ? (
            <><AlertTriangle className="w-3 h-3 mr-2" /> Connection Failed</>
          ) : (
            <><Activity className="w-3 h-3 mr-2 animate-spin" /> Connecting...</>
          )}
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="bg-surface border border-border-primary rounded-xl p-3 shadow-subtle flex items-center gap-4">
        <div className="flex items-center text-sm text-content-muted">
          <Filter className="w-4 h-4 mr-2" />
          <span>Filters:</span>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-content-secondary">Min Overall Score:</label>
          <select 
            className="text-sm bg-surface-secondary border border-border-primary rounded-lg px-2 py-1 focus:outline-none focus:border-accent-primary"
            value={minScoreFilter}
            onChange={(e) => setMinScoreFilter(Number(e.target.value))}
          >
            <option value={0}>All Scores</option>
            <option value={0.6}>&gt; 0.60</option>
            <option value={0.8}>&gt; 0.80</option>
            <option value={0.9}>&gt; 0.90</option>
          </select>
        </div>
      </div>

      {/* Feed List */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-2">
        {filteredEvents.length === 0 ? (
          <div className="h-40 flex flex-col items-center justify-center text-content-muted border border-dashed border-border-primary rounded-xl bg-surface/50">
            <Activity className="w-8 h-8 mb-2 opacity-50" />
            <p className="text-sm">Waiting for incoming evaluations...</p>
            <p className="text-xs mt-1">Run a query in the playground to trigger an evaluation.</p>
          </div>
        ) : (
          filteredEvents.map((evt, idx) => (
            <div key={idx} className="bg-surface border border-border-primary rounded-xl p-5 shadow-subtle animate-in slide-in-from-top-4 duration-300">
              <div className="flex justify-between items-start mb-4">
                <div className="flex-1 pr-4">
                  <div className="flex items-center mb-1">
                    <span className="text-xs font-semibold px-2 py-0.5 bg-surface-secondary border border-border-primary rounded text-content-secondary">
                      {getPipelineName(evt.pipeline_id)}
                    </span>
                    <span className="flex items-center text-xs text-content-muted ml-3">
                      <Clock className="w-3 h-3 mr-1" />
                      {new Date(evt.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                  <p className="text-sm font-medium text-content-primary leading-snug">"{evt.query}"</p>
                </div>
                <div className="flex flex-col items-end">
                  <span className="text-xs font-medium text-content-secondary uppercase tracking-wider mb-1">Overall</span>
                  <div className={`text-2xl font-bold font-mono ${getScoreColor(evt.overall_score)}`}>
                    {evt.overall_score.toFixed(2)}
                  </div>
                </div>
              </div>

              {/* Metric Breakdown */}
              <div className="grid grid-cols-2 gap-x-8 gap-y-2 pt-4 border-t border-border-primary">
                <MetricBar label="Faithfulness" score={evt.metrics.faithfulness} />
                <MetricBar label="Relevance" score={evt.metrics.relevance} />
                <MetricBar label="Precision" score={evt.metrics.precision} />
                <MetricBar label="Recall" score={evt.metrics.recall} />
              </div>
            </div>
          ))
        )}
      </div>

    </div>
  );
}
