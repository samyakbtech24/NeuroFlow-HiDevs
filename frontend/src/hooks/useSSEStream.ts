import { useState, useEffect, useCallback } from 'react';

export interface Citation {
  document_id: string;
  filename: string;
  content: string;
  score: number;
}

export function useSSEStream() {
  const [text, setText] = useState('');
  const [citations, setCitations] = useState<Citation[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startStream = useCallback((runId: string) => {
    setText('');
    setCitations([]);
    setIsStreaming(true);
    setError(null);

    const eventSource = new EventSource(`http://localhost:8000/runs/${runId}/stream`);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        if (data.type === 'chunk') {
          setText((prev) => prev + data.content);
        } else if (data.type === 'citations') {
          setCitations(data.citations);
        } else if (data.type === 'error') {
          setError(data.message);
          eventSource.close();
          setIsStreaming(false);
        }
      } catch (err) {
        console.error("Failed to parse SSE chunk", err);
      }
    };

    eventSource.onerror = () => {
      eventSource.close();
      setIsStreaming(false);
    };

    return () => {
      eventSource.close();
      setIsStreaming(false);
    };
  }, []);

  return { text, citations, isStreaming, error, startStream };
}
