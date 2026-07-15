'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { usePlaygroundStore } from '@/store/usePlaygroundStore';
import ResponsePanel from '@/components/ResponsePanel';
import { Play, SplitSquareHorizontal, Workflow } from 'lucide-react';

interface Pipeline {
  id: string;
  name: string;
  version: number;
  avg_score: number | null;
}

export default function PlaygroundPage() {
  const store = usePlaygroundStore();
  
  const [run1Id, setRun1Id] = useState<string | null>(null);
  const [run2Id, setRun2Id] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Fetch Pipelines
  const { data: pipelines = [], isLoading } = useQuery<Pipeline[]>({
    queryKey: ['pipelines'],
    queryFn: async () => {
      const res = await api.get('/pipelines');
      return res.data;
    }
  });

  const handleRun = async () => {
    if (!store.queryText.trim() || !store.pipeline1Id) return;
    
    setIsSubmitting(true);
    setRun1Id(null);
    setRun2Id(null);

    try {
      // Start primary pipeline
      const res1 = await api.post('/query', {
        query: store.queryText,
        pipeline_id: store.pipeline1Id,
        stream: true
      });
      setRun1Id(res1.data.run_id);

      // Start secondary pipeline if in compare mode
      if (store.isCompareMode && store.pipeline2Id) {
        const res2 = await api.post('/query', {
          query: store.queryText,
          pipeline_id: store.pipeline2Id,
          stream: true
        });
        setRun2Id(res2.data.run_id);
      }
    } catch (err) {
      console.error("Failed to start queries", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="w-full h-full flex flex-col space-y-6">
      
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-semibold text-content-primary tracking-tight">Query Playground</h1>
        <p className="text-content-secondary mt-1 text-sm">Test and compare pipeline configurations in real-time.</p>
      </div>
      
      {/* Controls & Input */}
      <div className="bg-surface border border-border-primary rounded-xl p-5 shadow-subtle space-y-5">
        
        {/* Pipeline Selectors */}
        <div className="flex gap-4">
          <div className="flex-1">
            <label className="block text-xs font-medium text-content-secondary mb-1.5 uppercase tracking-wider">Primary Pipeline</label>
            <div className="relative">
              <Workflow className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-content-muted" />
              <select 
                className="w-full pl-9 pr-3 py-2 text-sm bg-surface-secondary border border-border-primary rounded-lg focus:outline-none focus:border-accent-primary focus:ring-1 focus:ring-accent-primary appearance-none"
                value={store.pipeline1Id || ''}
                onChange={(e) => store.setPipeline1Id(e.target.value)}
                disabled={isLoading}
              >
                <option value="" disabled>Select a pipeline...</option>
                {pipelines.map(p => (
                  <option key={p.id} value={p.id}>
                    {p.name} v{p.version} {p.avg_score ? `(Score: ${p.avg_score.toFixed(2)})` : ''}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {store.isCompareMode && (
            <div className="flex-1">
              <label className="block text-xs font-medium text-content-secondary mb-1.5 uppercase tracking-wider">Comparison Pipeline</label>
              <div className="relative">
                <Workflow className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-content-muted" />
                <select 
                  className="w-full pl-9 pr-3 py-2 text-sm bg-surface-secondary border border-border-primary rounded-lg focus:outline-none focus:border-accent-primary focus:ring-1 focus:ring-accent-primary appearance-none"
                  value={store.pipeline2Id || ''}
                  onChange={(e) => store.setPipeline2Id(e.target.value)}
                  disabled={isLoading}
                >
                  <option value="" disabled>Select a pipeline...</option>
                  {pipelines.map(p => (
                    <option key={p.id} value={p.id}>
                      {p.name} v{p.version} {p.avg_score ? `(Score: ${p.avg_score.toFixed(2)})` : ''}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}
        </div>

        {/* Query Input */}
        <div>
          <textarea 
            className="w-full h-32 p-4 text-sm bg-surface-secondary border border-border-primary rounded-lg focus:outline-none focus:border-accent-primary focus:ring-1 focus:ring-accent-primary resize-none placeholder:text-content-muted"
            placeholder="Enter your prompt or question here..."
            value={store.queryText}
            onChange={(e) => store.setQueryText(e.target.value)}
          />
          <div className="flex justify-between items-center mt-3">
            <div className="flex items-center space-x-4">
              <label className="flex items-center text-sm text-content-secondary cursor-pointer">
                <input 
                  type="checkbox" 
                  className="hidden" 
                  checked={store.isCompareMode}
                  onChange={store.toggleCompareMode}
                />
                <div className={`w-10 h-5 rounded-full p-0.5 transition-colors ${store.isCompareMode ? 'bg-accent-primary' : 'bg-content-muted'}`}>
                  <div className={`w-4 h-4 bg-white rounded-full shadow-sm transition-transform ${store.isCompareMode ? 'translate-x-5' : 'translate-x-0'}`} />
                </div>
                <span className="ml-2 flex items-center font-medium">
                  <SplitSquareHorizontal className="w-4 h-4 mr-1.5" />
                  Compare Mode
                </span>
              </label>
              <span className="text-xs text-content-muted">{store.queryText.length} characters</span>
            </div>
            
            <button 
              onClick={handleRun}
              disabled={isSubmitting || !store.pipeline1Id || !store.queryText.trim()}
              className="flex items-center px-5 py-2 bg-accent-primary hover:bg-[#4A6BE0] text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
            >
              <Play className="w-4 h-4 mr-2" fill="currentColor" />
              {isSubmitting ? 'Starting...' : 'Run Query'}
            </button>
          </div>
        </div>
      </div>

      {/* Response Area */}
      <div className={`flex-1 min-h-0 ${store.isCompareMode ? 'grid grid-cols-2 gap-6' : ''}`}>
        <ResponsePanel 
          pipelineName={pipelines.find(p => p.id === store.pipeline1Id)?.name || 'Primary'} 
          runId={run1Id} 
        />
        {store.isCompareMode && (
          <ResponsePanel 
            pipelineName={pipelines.find(p => p.id === store.pipeline2Id)?.name || 'Comparison'} 
            runId={run2Id} 
          />
        )}
      </div>

    </div>
  );
}
