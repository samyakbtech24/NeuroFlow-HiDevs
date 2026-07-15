'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { 
  TerminalSquare, 
  Workflow, 
  Activity, 
  Files, 
  Settings, 
  Search,
  CheckCircle2,
  BrainCircuit
} from 'lucide-react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

// Utility for cleaner tailwind class merging
function cn(...inputs: (string | undefined | null | false)[]) {
  return twMerge(clsx(inputs));
}

const navItems = [
  { name: 'Playground', href: '/playground', icon: TerminalSquare },
  { name: 'Pipelines', href: '/pipelines', icon: Workflow },
  { name: 'Evaluations', href: '/evaluations', icon: Activity },
  { name: 'Documents', href: '/documents', icon: Files },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <div className="w-[270px] h-full flex flex-col bg-surface border-r border-border-primary shrink-0">
      
      {/* Logo Area */}
      <div className="h-16 flex items-center px-6 border-b border-border-primary">
        <BrainCircuit className="w-6 h-6 text-accent-primary mr-3" strokeWidth={1.5} />
        <span className="font-semibold text-content-primary tracking-tight">NeuroFlow</span>
      </div>

      {/* Search (Visual Only) */}
      <div className="px-4 py-4">
        <div className="flex items-center px-3 py-2 bg-surface-secondary border border-border-primary rounded-lg text-content-muted text-sm">
          <Search className="w-4 h-4 mr-2" strokeWidth={1.5} />
          <span>Search...</span>
          <div className="ml-auto flex items-center gap-1 text-xs">
            <kbd className="font-mono bg-surface border border-border-primary rounded px-1.5 py-0.5">⌘</kbd>
            <kbd className="font-mono bg-surface border border-border-primary rounded px-1.5 py-0.5">K</kbd>
          </div>
        </div>
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 px-3 space-y-1">
        {navItems.map((item) => {
          const isActive = pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.name}
              href={item.href}
              className={cn(
                "flex items-center px-3 py-2 text-sm font-medium rounded-lg transition-colors duration-200 relative group",
                isActive 
                  ? "bg-[#F0F4FF] text-accent-primary" 
                  : "text-content-secondary hover:bg-surface-secondary hover:text-content-primary"
              )}
            >
              {isActive && (
                <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-4 bg-accent-primary rounded-r-full" />
              )}
              <Icon className={cn("w-4 h-4 mr-3", isActive ? "text-accent-primary" : "text-content-muted group-hover:text-content-primary")} strokeWidth={1.5} />
              {item.name}
            </Link>
          );
        })}
      </nav>

      {/* Divider */}
      <div className="px-4 my-2">
        <div className="h-px w-full bg-border-primary" />
      </div>

      {/* Settings */}
      <div className="px-3 pb-2">
        <Link
          href="#"
          className="flex items-center px-3 py-2 text-sm font-medium rounded-lg text-content-secondary hover:bg-surface-secondary hover:text-content-primary transition-colors duration-200"
        >
          <Settings className="w-4 h-4 mr-3 text-content-muted" strokeWidth={1.5} />
          Settings
        </Link>
      </div>

      {/* System Status & User Profile */}
      <div className="p-4 border-t border-border-primary bg-surface-secondary/50">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center text-xs font-medium text-content-secondary">
            <div className="relative flex h-2 w-2 mr-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-status-success opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-status-success"></span>
            </div>
            All systems operational
          </div>
        </div>
        
        <div className="flex items-center">
          <div className="w-8 h-8 rounded-full bg-accent-secondary flex items-center justify-center text-white font-medium text-sm">
            JD
          </div>
          <div className="ml-3">
            <p className="text-sm font-medium text-content-primary">Jane Developer</p>
            <p className="text-xs text-content-muted">Admin Workspace</p>
          </div>
        </div>
      </div>

    </div>
  );
}
