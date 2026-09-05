"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function Sidebar() {
  const pathname = usePathname();

  const isDashboard = pathname === "/";
  const isExplorer = pathname === "/explorer";
  const isSandbox = pathname === "/sandbox";

  return (
    <nav className="fixed left-0 top-0 h-full flex flex-col w-64 border-r border-outline-variant bg-surface z-50">
      {/* Header */}
      <div className="p-6 border-b border-outline-variant flex items-center gap-4">
        <img
          alt="User Profile Avatar"
          className="w-10 h-10 rounded-full border border-outline-variant object-cover"
          src="https://lh3.googleusercontent.com/aida-public/AB6AXuAx6S8Yvwy3yGEULcyWL3y1B9tUB9YGkOWmz065NoPnXlKQg_u8UTq4Vq3z53RlMnaL7tW388o7AllgA2uXR9WM09e8UmE7RE9iz06bSRB016AdoTT1b3BJEFTsilkt6wJ3VBSHcFB3NC0ofkGE4bLRKWzjBf61-5aZpKIlma_mLXFcqjMdI1KMFXW99s6_lz4jo4e_d6uxWCLmFdlJRfPxiE9vfOhOWJCr7OdmSbLt6NfQ6MFWprI3dw"
        />
        <div>
          <h1 className="font-headline-md text-headline-md font-bold text-on-surface">
            Revenue Recovery Agent
          </h1>
          <p className="font-label-caps text-label-caps text-on-surface-variant">
            Recovery Specialist
          </p>
        </div>
      </div>
      
      {/* Navigation Tabs */}
      <div className="flex-1 py-4 flex flex-col gap-1 overflow-y-auto custom-scrollbar">
        <Link
          href="/"
          className={`flex items-center gap-3 px-4 py-3 transition-colors duration-200 ${
            isDashboard
              ? "text-primary font-bold border-r-2 border-primary bg-surface-container-high opacity-90"
              : "text-on-surface-variant hover:bg-surface-container-low"
          }`}
        >
          <span
            className="material-symbols-outlined"
            style={isDashboard ? { fontVariationSettings: "'FILL' 1" } : {}}
          >
            dashboard
          </span>
          <span className="font-label-caps text-label-caps">Dashboard</span>
        </Link>
        <Link
          href="/explorer"
          className={`flex items-center gap-3 px-4 py-3 transition-colors duration-200 ${
            isExplorer
              ? "text-primary font-bold border-r-2 border-primary bg-surface-container-high opacity-90"
              : "text-on-surface-variant hover:bg-surface-container-low"
          }`}
        >
          <span
            className="material-symbols-outlined"
            style={isExplorer ? { fontVariationSettings: "'FILL' 1" } : {}}
          >
            folder_open
          </span>
          <span className="font-label-caps text-label-caps">Case Explorer</span>
        </Link>
        <Link
          href="/sandbox"
          className={`flex items-center gap-3 px-4 py-3 transition-colors duration-200 ${
            isSandbox
              ? "text-primary font-bold border-r-2 border-primary bg-surface-container-high opacity-90"
              : "text-on-surface-variant hover:bg-surface-container-low"
          }`}
        >
          <span
            className="material-symbols-outlined"
            style={isSandbox ? { fontVariationSettings: "'FILL' 1" } : {}}
          >
            play_circle
          </span>
          <span className="font-label-caps text-label-caps">Live Interaction</span>
        </Link>
      </div>
      
      {/* Footer Tabs */}
      <div className="p-4 border-t border-outline-variant flex flex-col gap-1">
        <Link
          href="/sandbox"
          className="w-full mb-4 bg-primary text-on-primary font-label-caps text-label-caps py-2 rounded flex items-center justify-center gap-2 hover:bg-primary-container hover:text-on-primary-container transition-colors"
        >
          <span className="material-symbols-outlined text-sm">play_circle</span>
          Live Interaction
        </Link>
        <a
          href="https://github.com/OFF-rtk/RevenueRecoveryAgent"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-3 px-4 py-2 text-on-surface-variant hover:bg-surface-container-low transition-colors duration-200"
        >
          <svg className="w-[24px] h-[24px] fill-current" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M12 .5C5.65.5.5 5.65.5 12c0 5.09 3.29 9.4 7.86 10.93.57.1.78-.25.78-.55 0-.27-.01-1.17-.02-2.12-3.2.7-3.88-1.36-3.88-1.36-.52-1.34-1.28-1.7-1.28-1.7-1.05-.72.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.76 2.7 1.25 3.36.96.1-.75.4-1.25.73-1.54-2.55-.29-5.24-1.28-5.24-5.69 0-1.26.45-2.29 1.19-3.09-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.18 1.18a11.1 11.1 0 0 1 5.79 0c2.2-1.49 3.17-1.18 3.17-1.18.63 1.59.23 2.76.11 3.05.74.8 1.19 1.83 1.19 3.09 0 4.42-2.7 5.4-5.26 5.68.42.36.78 1.08.78 2.17 0 1.57-.01 2.83-.01 3.22 0 .3.2.66.79.55A10.52 10.52 0 0 0 23.5 12c0-6.35-5.15-11.5-11.5-11.5Z" />
          </svg>
          <span className="font-label-caps text-label-caps">GitHub</span>
        </a>
      </div>
    </nav>
  );
}
