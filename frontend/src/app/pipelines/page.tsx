'use client';

import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import CreatePipelineModal from '@/components/CreatePipelineModal';
import PipelineDrawer from '@/components/PipelineDrawer';
import { Plus, Workflow, Activity } from 'lucide-react';

export default function PipelinesPage() {
  const queryClient = useQueryClient();
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [selectedPipeline, setSelectedPipeline] = useState<any | null>(null);

  const { data: pipelines = [], isLoading } = useQuery({
    queryKey: ['pipelines'],
    queryFn: async () => {
      const res = await api.get('/pipelines');
      return res.data;
    }
  });

  const handleCreateSuccess = () => {
    setIsCreateModalOpen(false);
    queryClient.invalidateQueries({ queryKey: ['pipelines'] });
  };

  const getScoreColor = (score: number | null) => {
    if (score === null) return 'text-content-muted';
    if (score > 0.8) return 'text-status-success';
    if (score >= 0.6) return 'text-status-warning';
    return 'text-status-danger';
  };

  return (
    <div className="w-full h-full flex flex-col space-y-6">
      
      {/* Page Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-semibold text-content-primary tracking-tight">Pipeline Manager</h1>
          <p className="text-content-secondary mt-1 text-sm">Design, version, and monitor RAG architecture pipelines.</p>
        </div>
        <button 
          onClick={() => setIsCreateModalOpen(true)}
          className="flex items-center px-4 py-2 bg-accent-primary hover:bg-[#4A6BE0] text-white text-sm font-medium rounded-lg transition-colors shadow-sm"
        >
          <Plus className="w-4 h-4 mr-2" />
          Create Pipeline
        </button>
      </div>
      
      {/* Content Grid */}
      {isLoading ? (
        <div className="flex-1 flex items-center justify-center text-content-muted">Loading pipelines...</div>
      ) : pipelines.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center text-content-muted border border-dashed border-border-primary rounded-xl p-8 bg-surface/50">
          <Workflow className="w-12 h-12 mb-4 text-content-muted/50" />
          <p className="text-sm font-medium text-content-primary">No pipelines found</p>
          <p className="text-xs mt-1">Create your first RAG pipeline to get started.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {pipelines.map((pipeline: any) => (
            <div 
              key={pipeline.id}
              onClick={() => setSelectedPipeline(pipeline)}
              className="group bg-surface border border-border-primary hover:border-accent-primary rounded-xl p-5 shadow-subtle cursor-pointer transition-all hover:shadow-md flex flex-col"
            >
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center">
                  <div className="p-2 bg-surface-secondary rounded-lg mr-3 group-hover:bg-[#F0F4FF] transition-colors">
                    <Workflow className="w-5 h-5 text-content-secondary group-hover:text-accent-primary transition-colors" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-content-primary truncate max-w-[150px]">{pipeline.name}</h3>
                    <p className="text-xs text-content-muted mt-0.5">Version {pipeline.version}</p>
                  </div>
                </div>
              </div>

              <div className="mt-auto grid grid-cols-2 gap-4 pt-4 border-t border-border-primary">
                <div>
                  <p className="text-xs font-medium text-content-secondary uppercase tracking-wider mb-1">Total Runs</p>
                  <p className="text-xl font-semibold text-content-primary font-mono">{pipeline.total_runs}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-content-secondary uppercase tracking-wider mb-1">Avg Score</p>
                  <p className={`text-xl font-semibold font-mono ${getScoreColor(pipeline.avg_score)}`}>
                    {pipeline.avg_score ? pipeline.avg_score.toFixed(2) : '--'}
                  </p>
                </div>
              </div>

              {/* Sparkline Mockup */}
              <div className="mt-4 pt-3 border-t border-border-primary flex items-center justify-between text-xs text-content-muted">
                <span className="flex items-center"><Activity className="w-3 h-3 mr-1" /> Last 7 Days</span>
                <div className="flex items-end gap-0.5 h-4">
                  <div className="w-1.5 bg-border-primary rounded-t-sm h-[40%]" />
                  <div className="w-1.5 bg-border-primary rounded-t-sm h-[60%]" />
                  <div className="w-1.5 bg-border-primary rounded-t-sm h-[30%]" />
                  <div className="w-1.5 bg-border-primary rounded-t-sm h-[80%]" />
                  <div className="w-1.5 bg-border-primary rounded-t-sm h-[50%]" />
                  <div className="w-1.5 bg-status-success/60 rounded-t-sm h-[90%]" />
                  <div className="w-1.5 bg-status-success rounded-t-sm h-[100%]" />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modals & Drawers */}
      {isCreateModalOpen && (
        <CreatePipelineModal 
          onClose={() => setIsCreateModalOpen(false)} 
          onSuccess={handleCreateSuccess} 
        />
      )}

      <PipelineDrawer 
        pipeline={selectedPipeline} 
        onClose={() => setSelectedPipeline(null)} 
      />

    </div>
  );
}
