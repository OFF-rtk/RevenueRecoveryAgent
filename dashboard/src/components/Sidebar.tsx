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
            Integrity Terminal
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
        <Link
          href="#"
          className="flex items-center gap-3 px-4 py-2 text-on-surface-variant hover:bg-surface-container-low transition-colors duration-200"
        >
          <span className="material-symbols-outlined">help_outline</span>
          <span className="font-label-caps text-label-caps">Support</span>
        </Link>
      </div>
    </nav>
  );
}
