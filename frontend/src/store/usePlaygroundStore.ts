import { create } from 'zustand';

interface PlaygroundState {
  isCompareMode: boolean;
  toggleCompareMode: () => void;
  
  pipeline1Id: string | null;
  setPipeline1Id: (id: string | null) => void;
  
  pipeline2Id: string | null;
  setPipeline2Id: (id: string | null) => void;
  
  queryText: string;
  setQueryText: (text: string) => void;
}

export const usePlaygroundStore = create<PlaygroundState>((set) => ({
  isCompareMode: false,
  toggleCompareMode: () => set((state) => ({ isCompareMode: !state.isCompareMode })),
  
  pipeline1Id: null,
  setPipeline1Id: (id) => set({ pipeline1Id: id }),
  
  pipeline2Id: null,
  setPipeline2Id: (id) => set({ pipeline2Id: id }),
  
  queryText: '',
  setQueryText: (text) => set({ queryText: text }),
}));
