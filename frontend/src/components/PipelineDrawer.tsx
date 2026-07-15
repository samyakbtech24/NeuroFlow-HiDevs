'use client';

import { X, AlertCircle } from 'lucide-react';
import { 
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, LineChart, Line
} from 'recharts';

interface PipelineDrawerProps {
  pipeline: any | null;
  onClose: () => void;
}

// Dummy data for visual layout purposes since backend doesn't serve timeseries yet
const radarData = [
  { metric: 'Faithfulness', score: 0.92 },
  { metric: 'Relevance', score: 0.88 },
  { metric: 'Precision', score: 0.75 },
  { metric: 'Recall', score: 0.81 },
];

const latencyData = [
  { percentile: 'P50', ms: 1200 },
  { percentile: 'P90', ms: 2800 },
  { percentile: 'P95', ms: 3400 },
  { percentile: 'P99', ms: 5200 },
];

const costData = [
  { day: 'Mon', cost: 1.2 },
  { day: 'Tue', cost: 1.5 },
  { day: 'Wed', cost: 2.1 },
  { day: 'Thu', cost: 1.8 },
  { day: 'Fri', cost: 2.4 },
  { day: 'Sat', cost: 0.8 },
  { day: 'Sun', cost: 0.9 },
];

export default function PipelineDrawer({ pipeline, onClose }: PipelineDrawerProps) {
  if (!pipeline) return null;

  return (
    <>
      {/* Backdrop */}
      <div 
        className="fixed inset-0 bg-black/20 backdrop-blur-[2px] z-40 transition-opacity"
        onClick={onClose}
      />
      
      {/* Drawer */}
      <div className="fixed inset-y-0 right-0 w-[500px] bg-surface border-l border-border-primary shadow-2xl z-50 flex flex-col animate-in slide-in-from-right duration-300">
        
        {/* Header */}
        <div className="px-6 py-5 border-b border-border-primary bg-surface-secondary flex items-center justify-between shrink-0">
          <div>
            <h2 className="text-lg font-semibold text-content-primary">{pipeline.name}</h2>
            <p className="text-sm text-content-muted mt-0.5">Version {pipeline.version} • Created {new Date(pipeline.created_at).toLocaleDateString()}</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-surface border border-transparent hover:border-border-primary rounded-lg text-content-muted transition-all">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-8">
          
          {/* Radar Chart */}
          <section>
            <h3 className="text-sm font-semibold text-content-secondary uppercase tracking-wider mb-4">Evaluation Performance</h3>
            <div className="h-[250px] w-full bg-surface-secondary border border-border-primary rounded-xl p-4">
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart cx="50%" cy="50%" outerRadius="80%" data={radarData}>
                  <PolarGrid stroke="#E6EAF0" />
                  <PolarAngleAxis dataKey="metric" tick={{ fill: '#667085', fontSize: 12 }} />
                  <PolarRadiusAxis angle={30} domain={[0, 1]} tick={{ fill: '#98A2B3', fontSize: 10 }} />
                  <Radar name="Score" dataKey="score" stroke="#5B7CFA" fill="#5B7CFA" fillOpacity={0.3} />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          </section>

          {/* Latency Histograms */}
          <section>
            <h3 className="text-sm font-semibold text-content-secondary uppercase tracking-wider mb-4">Latency Distribution</h3>
            <div className="h-[200px] w-full bg-surface-secondary border border-border-primary rounded-xl p-4">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={latencyData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E6EAF0" />
                  <XAxis dataKey="percentile" tick={{ fill: '#667085', fontSize: 12 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: '#98A2B3', fontSize: 12 }} axisLine={false} tickLine={false} />
                  <Tooltip cursor={{ fill: 'rgba(0,0,0,0.02)' }} contentStyle={{ borderRadius: '8px', border: '1px solid #E6EAF0' }} />
                  <Bar dataKey="ms" fill="#B7A9FF" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>

          {/* Cost Trend */}
          <section>
            <h3 className="text-sm font-semibold text-content-secondary uppercase tracking-wider mb-4">Cost Trend (Last 7 Days)</h3>
            <div className="h-[200px] w-full bg-surface-secondary border border-border-primary rounded-xl p-4">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={costData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E6EAF0" />
                  <XAxis dataKey="day" tick={{ fill: '#667085', fontSize: 12 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: '#98A2B3', fontSize: 12 }} axisLine={false} tickLine={false} tickFormatter={(val) => `$${val}`} />
                  <Tooltip cursor={{ stroke: '#E6EAF0' }} contentStyle={{ borderRadius: '8px', border: '1px solid #E6EAF0' }} />
                  <Line type="monotone" dataKey="cost" stroke="#7BC47F" strokeWidth={2} dot={{ r: 4, fill: '#7BC47F' }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </section>

          {/* Recent Failures */}
          <section>
            <h3 className="text-sm font-semibold text-content-secondary uppercase tracking-wider mb-4">Recent Anomalies</h3>
            <div className="space-y-3">
              <div className="p-3 bg-red-50 border border-status-danger/30 rounded-lg flex items-start">
                <AlertCircle className="w-4 h-4 text-status-danger mt-0.5 mr-2 shrink-0" />
                <div>
                  <p className="text-sm font-medium text-status-danger">RateLimitExceeded</p>
                  <p className="text-xs text-status-danger/80 mt-1">OpenAI global token bucket depleted during traffic spike.</p>
                  <p className="text-[10px] text-status-danger/60 mt-1 uppercase">2 hours ago</p>
                </div>
              </div>
            </div>
          </section>

        </div>
      </div>
    </>
  );
}
