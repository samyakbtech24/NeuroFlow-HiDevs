'use client';

import { useState } from 'react';
import Editor from '@monaco-editor/react';
import { X, Save } from 'lucide-react';
import { api } from '@/lib/api';

interface CreatePipelineModalProps {
  onClose: () => void;
  onSuccess: () => void;
}

const DEFAULT_CONFIG = {
  model: "gpt-4o-mini",
  temperature: 0.0,
  max_tokens: 1000,
  retrieval: {
    top_k: 5,
    similarity_threshold: 0.75
  },
  rate_limit_rpm: 60
};

export default function CreatePipelineModal({ onClose, onSuccess }: CreatePipelineModalProps) {
  const [name, setName] = useState('');
  const [configStr, setConfigStr] = useState(JSON.stringify(DEFAULT_CONFIG, null, 2));
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSave = async () => {
    setError(null);
    if (!name.trim()) {
      setError("Pipeline name is required.");
      return;
    }
    
    let parsedConfig;
    try {
      parsedConfig = JSON.parse(configStr);
    } catch (err) {
      setError("Invalid JSON configuration.");
      return;
    }

    setIsSubmitting(true);
    try {
      await api.post('/pipelines', {
        name,
        ...parsedConfig
      });
      onSuccess();
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to create pipeline");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-surface w-full max-w-3xl rounded-xl shadow-xl flex flex-col overflow-hidden border border-border-primary animate-in fade-in zoom-in-95 duration-200">
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border-primary bg-surface-secondary">
          <h2 className="text-lg font-semibold text-content-primary">Create New Pipeline</h2>
          <button onClick={onClose} className="p-1.5 hover:bg-surface rounded-lg text-content-muted hover:text-content-primary transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 p-6 space-y-6">
          {error && (
            <div className="p-3 bg-red-50 border border-status-danger/30 rounded-lg text-sm text-status-danger font-medium">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-content-secondary mb-1.5">Pipeline Name</label>
            <input 
              type="text" 
              className="w-full px-4 py-2 bg-surface-secondary border border-border-primary rounded-lg focus:outline-none focus:border-accent-primary focus:ring-1 focus:ring-accent-primary text-sm text-content-primary"
              placeholder="e.g. production-gpt4o-v2"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div>
            <div className="flex justify-between items-end mb-1.5">
              <label className="block text-sm font-medium text-content-secondary">Pipeline Configuration (JSON)</label>
              <span className="text-xs text-content-muted font-mono">Validated against PipelineConfig Schema</span>
            </div>
            <div className="h-[300px] border border-border-primary rounded-lg overflow-hidden focus-within:border-accent-primary focus-within:ring-1 focus-within:ring-accent-primary transition-all">
              <Editor
                height="100%"
                defaultLanguage="json"
                value={configStr}
                onChange={(val) => setConfigStr(val || '')}
                theme="light"
                options={{
                  minimap: { enabled: false },
                  fontSize: 13,
                  fontFamily: 'var(--font-jetbrains-mono)',
                  formatOnPaste: true,
                  scrollBeyondLastLine: false,
                }}
              />
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-border-primary bg-surface-secondary flex justify-end gap-3">
          <button 
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-content-secondary hover:text-content-primary bg-surface border border-border-primary hover:bg-surface-secondary rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button 
            onClick={handleSave}
            disabled={isSubmitting}
            className="flex items-center px-4 py-2 text-sm font-medium text-white bg-accent-primary hover:bg-[#4A6BE0] rounded-lg transition-colors disabled:opacity-50"
          >
            <Save className="w-4 h-4 mr-2" />
            {isSubmitting ? 'Saving...' : 'Save Pipeline'}
          </button>
        </div>

      </div>
    </div>
  );
}
