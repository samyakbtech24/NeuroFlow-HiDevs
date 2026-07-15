'use client';

import { useState, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { UploadCloud, File as FileIcon, Image as ImageIcon, Link as LinkIcon, FileText, CheckCircle2, Clock, AlertTriangle } from 'lucide-react';

export default function DocumentsPage() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Poll documents every 5 seconds to update processing status
  const { data: documents = [], isLoading } = useQuery({
    queryKey: ['documents'],
    queryFn: async () => {
      const res = await api.get('/ingest');
      return res.data;
    },
    refetchInterval: 5000,
  });

  const handleUpload = async (file: File) => {
    setUploading(true);
    setError(null);
    const formData = new FormData();
    formData.append('file', file);

    try {
      await api.post('/ingest', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      queryClient.invalidateQueries({ queryKey: ['documents'] });
    } catch (err: any) {
      setError(err.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const getSourceIcon = (type: string) => {
    if (type === 'pdf' || type === 'docx') return <FileText className="w-4 h-4 text-accent-primary" />;
    if (type === 'image') return <ImageIcon className="w-4 h-4 text-accent-secondary" />;
    if (type === 'url') return <LinkIcon className="w-4 h-4 text-content-secondary" />;
    return <FileIcon className="w-4 h-4 text-content-muted" />;
  };

  const StatusBadge = ({ status }: { status: string }) => {
    if (status === 'completed') {
      return (
        <span className="flex items-center text-xs font-medium text-status-success bg-status-success/10 px-2 py-1 rounded-md border border-status-success/20">
          <CheckCircle2 className="w-3 h-3 mr-1.5" /> Ready
        </span>
      );
    }
    if (status === 'failed') {
      return (
        <span className="flex items-center text-xs font-medium text-status-danger bg-status-danger/10 px-2 py-1 rounded-md border border-status-danger/20">
          <AlertTriangle className="w-3 h-3 mr-1.5" /> Failed
        </span>
      );
    }
    // Processing or Queued
    return (
      <span className="flex items-center text-xs font-medium text-accent-primary bg-[#F0F4FF] px-2 py-1 rounded-md border border-accent-primary/20">
        <div className="relative flex h-2 w-2 mr-1.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent-primary opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2 w-2 bg-accent-primary"></span>
        </div>
        Processing
      </span>
    );
  };

  return (
    <div className="w-full h-full flex flex-col space-y-6">
      
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-content-primary tracking-tight">Knowledge Base</h1>
        <p className="text-content-secondary mt-1 text-sm">Upload documents to expand NeuroFlow's RAG retrieval context.</p>
      </div>

      {/* Upload Zone */}
      <div 
        className={`w-full p-8 border-2 border-dashed rounded-xl flex flex-col items-center justify-center transition-colors ${
          isDragging ? 'border-accent-primary bg-[#F0F4FF]' : 'border-border-primary bg-surface hover:bg-surface-secondary'
        }`}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            handleUpload(e.dataTransfer.files[0]);
          }
        }}
      >
        <div className="p-3 bg-surface border border-border-primary rounded-full mb-3 shadow-subtle">
          <UploadCloud className="w-6 h-6 text-content-secondary" />
        </div>
        <p className="text-sm font-medium text-content-primary">Click to upload or drag and drop</p>
        <p className="text-xs text-content-muted mt-1">PDF, DOCX, CSV, or Images (max. 10MB)</p>
        
        <input 
          type="file" 
          className="hidden" 
          ref={fileInputRef}
          onChange={(e) => e.target.files && handleUpload(e.target.files[0])}
        />
        <button 
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          className="mt-4 px-4 py-2 bg-surface border border-border-primary hover:border-accent-primary text-sm font-medium text-content-primary rounded-lg transition-colors disabled:opacity-50"
        >
          {uploading ? 'Uploading...' : 'Select File'}
        </button>
        {error && <p className="text-xs font-medium text-status-danger mt-3">{error}</p>}
      </div>

      {/* Document Table */}
      <div className="flex-1 bg-surface border border-border-primary rounded-xl shadow-subtle overflow-hidden flex flex-col">
        <div className="px-5 py-4 border-b border-border-primary bg-surface-secondary">
          <h2 className="text-sm font-semibold text-content-primary">Indexed Documents</h2>
        </div>
        
        <div className="flex-1 overflow-auto">
          <table className="w-full text-left border-collapse">
            <thead className="sticky top-0 bg-surface border-b border-border-primary z-10">
              <tr>
                <th className="px-5 py-3 text-xs font-medium text-content-secondary uppercase tracking-wider">File Name</th>
                <th className="px-5 py-3 text-xs font-medium text-content-secondary uppercase tracking-wider">Status</th>
                <th className="px-5 py-3 text-xs font-medium text-content-secondary uppercase tracking-wider">Chunks</th>
                <th className="px-5 py-3 text-xs font-medium text-content-secondary uppercase tracking-wider text-right">Ingested</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-primary">
              {isLoading ? (
                <tr><td colSpan={4} className="px-5 py-8 text-center text-sm text-content-muted">Loading documents...</td></tr>
              ) : documents.length === 0 ? (
                <tr><td colSpan={4} className="px-5 py-8 text-center text-sm text-content-muted">No documents found. Upload one above.</td></tr>
              ) : (
                documents.map((doc: any) => (
                  <tr key={doc.id} className="hover:bg-surface-secondary transition-colors group cursor-pointer">
                    <td className="px-5 py-3">
                      <div className="flex items-center">
                        <div className="w-8 h-8 rounded bg-surface-secondary border border-border-primary flex items-center justify-center mr-3 group-hover:border-accent-primary/50 transition-colors">
                          {getSourceIcon(doc.source_type)}
                        </div>
                        <span className="text-sm font-medium text-content-primary truncate max-w-[300px]" title={doc.filename}>{doc.filename}</span>
                      </div>
                    </td>
                    <td className="px-5 py-3"><StatusBadge status={doc.status} /></td>
                    <td className="px-5 py-3 text-sm text-content-secondary font-mono">{doc.chunk_count || '--'}</td>
                    <td className="px-5 py-3 text-sm text-content-secondary text-right">
                      {new Date(doc.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

    </div>
  );
}
