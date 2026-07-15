'use client';

import { useEffect, useState } from 'react';
import { useSSEStream } from '@/hooks/useSSEStream';
import { FileText, CheckCircle2, ChevronRight, ThumbsUp, ThumbsDown } from 'lucide-react';
import { api } from '@/lib/api';

interface ResponsePanelProps {
  pipelineName: string;
  runId: string | null;
}

export default function ResponsePanel({ pipelineName, runId }: ResponsePanelProps) {
  const { text, citations, isStreaming, error, startStream } = useSSEStream();
  const [feedback, setFeedback] = useState<'up' | 'down' | null>(null);

  useEffect(() => {
    if (runId) {
      setFeedback(null);
      startStream(runId);
    }
  }, [runId, startStream]);

  const handleFeedback = async (type: 'up' | 'down') => {
    if (!runId) return;
    setFeedback(type);
    try {
      await api.patch(`/runs/${runId}/rating`, {
        rating: type === 'up' ? 5 : 1
      });
    } catch (err) {
      console.error("Failed to submit feedback", err);
    }
  };

  if (!runId && !isStreaming && !text) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-content-muted border border-dashed border-border-primary rounded-xl p-8 bg-surface/50">
        <p className="text-sm">Select a pipeline and submit a query to see the response.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-surface border border-border-primary rounded-xl overflow-hidden shadow-subtle">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border-primary bg-surface-secondary flex items-center justify-between">
        <div className="flex items-center">
          <div className="w-2 h-2 rounded-full bg-accent-primary mr-2" />
          <span className="text-sm font-semibold text-content-primary">{pipelineName}</span>
        </div>
        {isStreaming ? (
          <span className="text-xs font-medium text-content-muted animate-pulse">Streaming...</span>
        ) : text ? (
          <span className="flex items-center text-xs font-medium text-status-success">
            <CheckCircle2 className="w-3 h-3 mr-1" />
            Complete
          </span>
        ) : null}
      </div>

      {/* Content Area */}
      <div className="flex-1 overflow-y-auto p-5 space-y-6">
        
        {/* Error State */}
        {error && (
          <div className="p-3 bg-red-50 border border-status-danger/30 rounded-lg text-sm text-status-danger">
            {error}
          </div>
        )}

        {/* Citations Preview (shows immediately as they arrive) */}
        {citations.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-xs font-semibold text-content-muted uppercase tracking-wider">Retrieved Context</h4>
            <div className="flex flex-wrap gap-2">
              {citations.map((cite, i) => (
                <button 
                  key={i}
                  className="flex items-center px-2 py-1 bg-surface-secondary border border-border-primary rounded hover:border-accent-primary transition-colors text-xs text-content-secondary"
                  title={cite.content}
                >
                  <FileText className="w-3 h-3 mr-1 text-content-muted" />
                  <span className="truncate max-w-[150px]">{cite.filename}</span>
                  <span className="ml-2 text-[10px] text-status-success bg-status-success/10 px-1 rounded">
                    {Math.round(cite.score * 100)}%
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Generated Answer */}
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-content-muted uppercase tracking-wider">Generated Answer</h4>
          <div className="prose prose-sm max-w-none text-content-primary leading-relaxed whitespace-pre-wrap">
            {text}
            {isStreaming && <span className="inline-block w-1.5 h-4 ml-1 bg-accent-primary animate-pulse" />}
          </div>
        </div>

      </div>

      {/* Footer / Actions */}
      {!isStreaming && text && (
        <div className="p-3 border-t border-border-primary bg-surface-secondary flex items-center justify-between">
          <span className="text-xs text-content-muted">Was this helpful?</span>
          <div className="flex gap-2">
            <button 
              onClick={() => handleFeedback('up')}
              className={`p-1.5 rounded transition-colors ${feedback === 'up' ? 'text-status-success bg-status-success/10' : 'text-content-muted hover:text-content-primary hover:bg-surface'}`}
            >
              <ThumbsUp className="w-4 h-4" />
            </button>
            <button 
              onClick={() => handleFeedback('down')}
              className={`p-1.5 rounded transition-colors ${feedback === 'down' ? 'text-status-danger bg-status-danger/10' : 'text-content-muted hover:text-content-primary hover:bg-surface'}`}
            >
              <ThumbsDown className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
