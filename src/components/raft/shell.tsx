"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeftRight,
  Bell,
  BookOpen,
  FileText,
  Landmark,
  LayoutGrid,
  MessagesSquare,
  PanelRight,
  Search,
  Settings,
  Tag,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useT } from "@/i18n";
import type { Dictionary } from "@/i18n/uz";
import { dataSourceStore } from "@/lib/api/client";
import { useActivity } from "@/lib/api/hooks";
import { ACCOUNTS, homeFor, setAccount, useAccount, type Account } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { CommandPalette } from "./command-palette";
import { CopilotPanel } from "./copilot-panel";

interface UndoState {
  text: string;
  onUndo: () => void;
}

interface CopilotContextValue {
  screen: string;
  selected_ids: string[];
}

interface ShellValue {
  account: Account;
  openPalette: () => void;
  copilotOpen: boolean;
  toggleCopilot: () => void;
  copilotContext: CopilotContextValue;
  setCopilotContext: (value: CopilotContextValue) => void;
  showUndo: (value: UndoState) => void;
}

const ShellContext = createContext<ShellValue | null>(null);

export function useShell() {
  const value = useContext(ShellContext);
  if (!value) throw new Error("useShell must be used inside the app shell");
  return value;
}

/** Tells the copilot which screen and rows the user is looking at. */
export function useCopilotScreen(screen: string, selectedIds: string[] = []) {
  const { setCopilotContext } = useShell();
  const key = selectedIds.join(",");
  useEffect(() => {
    setCopilotContext({ screen, selected_ids: key ? key.split(",") : [] });
  }, [screen, key, setCopilotContext]);
}

export interface NavItem {
  href: string;
  label: keyof Dictionary["nav"];
  icon: LucideIcon;
  match: string;
}

export function navFor(account: Account): NavItem[] {
  if (account.kind === "bank") {
    return [
      { href: "/partner", label: "arizalar", icon: FileText, match: "/partner$" },
      { href: "/partner/garov", label: "garov", icon: Landmark, match: "/partner/garov" },
      { href: "/partner/hisobot", label: "hisobot", icon: ArrowLeftRight, match: "/partner/hisobot" },
    ];
  }
  if (account.kind === "bazaar") return [{ href: "/partner", label: "hisobot", icon: ArrowLeftRight, match: "/partner" }];
  if (account.kind === "supplier") return [{ href: "/birja", label: "birja", icon: ArrowLeftRight, match: "/birja" }];
  return [
    { href: "/bugun", label: "bugun", icon: LayoutGrid, match: "/bugun" },
    { href: "/narxlar", label: "narxlar", icon: Tag, match: "/narxlar" },
    { href: "/birja", label: "birja", icon: ArrowLeftRight, match: "/birja" },
    { href: "/kitoblar", label: "kitoblar", icon: BookOpen, match: "/kitoblar" },
    { href: "/maslahat", label: "maslahat", icon: MessagesSquare, match: "/maslahat" },
  ];
}

function allowed(account: Account, path: string) {
  if (path === "/model" || path === "/sozlama") return true;
  if (account.kind === "bank" || account.kind === "bazaar") return path.startsWith("/partner");
  if (account.kind === "supplier") return path.startsWith("/birja");
  return !path.startsWith("/partner");
}

function NavLink({ item, active, label }: { item: Pick<NavItem, "href" | "icon">; active: boolean; label: string }) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex h-[60px] w-[72px] flex-col items-center justify-center gap-1 rounded-[28px] text-[11px] leading-[14px] text-text-2 transition-colors duration-150 hover:text-text max-md:h-12 max-md:w-auto max-md:flex-1 max-md:rounded-[16px]",
        active && "bg-accent-soft font-medium text-accent-text hover:text-accent-text",
      )}
    >
      <Icon size={20} strokeWidth={1.75} aria-hidden />
      <span className="max-w-full truncate">{label}</span>
    </Link>
  );
}

function AccountSwitcher({ account }: { account: Account }) {
  const t = useT();
  const router = useRouter();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);

  const choose = (next: Account) => {
    setOpen(false);
    setAccount(next.id);
    qc.clear();
    router.push(homeFor(next));
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        aria-label={t.shell.account}
        className="flex h-11 w-11 items-center justify-center rounded-full bg-white/85 text-[13px] font-semibold transition-colors duration-150 hover:bg-white"
      >
        {account.initials}
      </PopoverTrigger>
      <PopoverContent side="right" align="end" className="w-[300px]">
        <p className="px-2 py-1 t-cap">{t.shell.account}</p>
        <ul>
          {ACCOUNTS.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                onClick={() => choose(item)}
                aria-current={item.id === account.id ? "true" : undefined}
                className={cn("flex min-h-11 w-full items-baseline justify-between gap-3 rounded-[12px] px-2 py-2 text-left text-[13px] hover:bg-[var(--nested)]", item.id === account.id && "bg-accent-soft")}
              >
                <span className="truncate-1 font-medium">{item.name}</span>
                <span className="t-cap shrink-0">{item.role}</span>
              </button>
            </li>
          ))}
        </ul>
        <button
          type="button"
          className="mt-1 min-h-11 w-full rounded-[12px] px-2 text-left text-[13px] text-text-2 hover:bg-[var(--nested)]"
          onClick={() => {
            setAccount(null);
            qc.clear();
            router.push("/login");
          }}
        >
          {t.shell.signOut}
        </button>
      </PopoverContent>
    </Popover>
  );
}

function Sidebar({ account }: { account: Account }) {
  const t = useT();
  const path = usePathname();
  const items = navFor(account);
  return (
    <nav
      aria-label="Asosiy menyu"
      className="glass sticky top-5 z-30 flex h-[calc(100vh-40px)] w-[88px] shrink-0 flex-col items-center rounded-[36px] py-5 max-md:fixed max-md:inset-x-4 max-md:top-auto max-md:bottom-4 max-md:h-16 max-md:w-auto max-md:flex-row max-md:gap-1 max-md:rounded-[28px] max-md:px-2 max-md:py-2"
    >
      <Link
        href={homeFor(account)}
        aria-label="Raft bosh sahifa"
        className="mb-5 flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-text text-[16px] font-semibold text-white max-md:hidden"
      >
        R
      </Link>
      <div className="flex flex-col items-center gap-1 max-md:flex-1 max-md:flex-row">
        {items.map((item) => (
          <NavLink key={item.href} item={item} label={t.nav[item.label]} active={new RegExp(`^${item.match}`).test(path)} />
        ))}
      </div>
      <div className="mt-auto flex flex-col items-center gap-2 max-md:mt-0 max-md:flex-row">
        <NavLink item={{ href: "/sozlama", icon: Settings }} label={t.nav.sozlama} active={path.startsWith("/sozlama")} />
        <AccountSwitcher account={account} />
      </div>
    </nav>
  );
}

function Notifications() {
  const t = useT();
  const query = useActivity();
  const items = query.data?.items.slice(0, 5) ?? [];
  const [seen, setSeen] = useState(0);
  const unread = items.length > 0 && (query.data?.items.length ?? 0) > seen;
  return (
    <Popover onOpenChange={(open) => open && setSeen(query.data?.items.length ?? 0)}>
      <PopoverTrigger className="icon-btn" aria-label={unread ? `${t.shell.notifications}: yangi xabar bor` : t.shell.notifications}>
        <Bell size={20} strokeWidth={1.75} aria-hidden />
        {unread ? <span className="absolute top-[11px] right-[11px] h-1.5 w-1.5 rounded-full bg-danger" /> : null}
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[340px]">
        <p className="px-2 py-1 t-cap">{t.shell.notifications}</p>
        {items.length === 0 ? (
          <p className="px-2 py-3 text-[13px] text-muted">{t.shell.noNotifications}</p>
        ) : (
          <ul>
            {items.map((row, i) => (
              <li key={`${row.text}-${i}`} className="flex items-baseline gap-3 px-2 py-2 text-[13px]">
                <span className="t-mono-cap w-11 shrink-0">{row.time}</span>
                <span className="min-w-0 flex-1">{row.text}</span>
              </li>
            ))}
          </ul>
        )}
      </PopoverContent>
    </Popover>
  );
}

export interface PageTab {
  key: string;
  label: string;
  href: string;
}

export function Page({
  title,
  subtitle,
  tabs,
  active,
  children,
}: {
  title: string;
  subtitle?: string;
  tabs?: PageTab[];
  active?: string;
  children: ReactNode;
}) {
  const t = useT();
  const { openPalette, toggleCopilot, copilotOpen, account } = useShell();
  const source = useSyncExternalStore(dataSourceStore.subscribe, dataSourceStore.get, dataSourceStore.getServer);
  const showCopilot = account.kind === "business";
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-5">
      <header className="glass relative z-20 flex min-h-16 flex-wrap items-center gap-x-4 gap-y-2 rounded-[36px] py-2 pr-3 pl-5">
        <h1 className="text-[17px] leading-[24px] font-semibold whitespace-nowrap">{title}</h1>
        {tabs ? (
          <nav aria-label={`${title} bo‘limlari`} className="seg max-w-full overflow-x-auto">
            {tabs.map((tab) => (
              <Link key={tab.key} href={tab.href} replace scroll={false} data-active={tab.key === active} aria-current={tab.key === active ? "page" : undefined} className="seg-item">
                {tab.label}
              </Link>
            ))}
          </nav>
        ) : null}
        {subtitle ? <p className="truncate-1 text-[14px] text-text-2">{subtitle}</p> : null}
        <div className="ml-auto flex items-center gap-1">
          {source === "fixtures" ? <span className="mr-3 hidden text-[12px] text-muted whitespace-nowrap lg:inline">{t.shell.demoData}</span> : null}
          <button
            type="button"
            onClick={openPalette}
            className="mr-1 flex h-10 w-[200px] items-center gap-2 rounded-[20px] border border-[rgb(15_23_22/0.06)] bg-white/70 px-3 text-[14px] text-muted transition-colors duration-150 hover:bg-white/90 max-lg:w-11 max-lg:justify-center max-lg:px-0 xl:w-[260px] 2xl:w-[320px]"
          >
            <Search size={16} strokeWidth={1.75} aria-hidden className="shrink-0" />
            <span className="max-lg:sr-only">{t.shell.search}</span>
            <span className="mono ml-auto text-[11px] max-lg:hidden">Ctrl K</span>
          </button>
          {showCopilot ? (
            <button type="button" className="icon-btn" aria-label={t.shell.copilot} aria-pressed={copilotOpen} onClick={toggleCopilot}>
              <PanelRight size={20} strokeWidth={1.75} aria-hidden />
            </button>
          ) : null}
          <Notifications />
        </div>
      </header>
      <main className="flex min-w-0 flex-1 flex-col gap-5">{children}</main>
    </div>
  );
}

function UndoBar({ undo, onClose }: { undo: UndoState; onClose: () => void }) {
  const t = useT();
  useEffect(() => {
    const timer = setTimeout(onClose, 5000);
    return () => clearTimeout(timer);
  }, [undo, onClose]);
  return (
    <div role="status" className="fade-in fixed bottom-5 left-1/2 z-50 flex -translate-x-1/2 items-center gap-4 rounded-[20px] bg-text py-1 pr-1 pl-5 text-[14px] text-white shadow-[var(--shadow-pop)] max-md:bottom-24">
      <span className="whitespace-nowrap">{undo.text}</span>
      <button
        type="button"
        className="h-11 rounded-[16px] px-4 font-semibold text-white hover:bg-white/10"
        onClick={() => {
          undo.onUndo();
          onClose();
        }}
      >
        {t.shell.undo}
      </button>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const account = useAccount();
  const path = usePathname();
  const router = useRouter();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [copilotContext, setCopilotContext] = useState<CopilotContextValue>({ screen: "bugun", selected_ids: [] });
  const [undo, setUndo] = useState<UndoState | null>(null);
  const closeUndo = useCallback(() => setUndo(null), []);
  const openerRef = useRef<HTMLElement | null>(null);

  const permitted = account ? allowed(account, path) : false;

  useEffect(() => {
    if (account === null) router.replace("/login");
    else if (account && !permitted) router.replace(homeFor(account));
  }, [account, permitted, router]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        openerRef.current = document.activeElement as HTMLElement | null;
        setPaletteOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const value = useMemo<ShellValue | null>(
    () =>
      account
        ? {
            account,
            openPalette: () => setPaletteOpen(true),
            copilotOpen,
            toggleCopilot: () => setCopilotOpen((v) => !v),
            copilotContext,
            setCopilotContext,
            showUndo: setUndo,
          }
        : null,
    [account, copilotOpen, copilotContext],
  );

  if (!account || !value || !permitted) {
    return (
      <div className="flex min-h-screen gap-5 p-5" aria-busy="true">
        <div className="glass h-[calc(100vh-40px)] w-[88px] shrink-0 rounded-[36px] max-md:hidden" />
        <div className="flex flex-1 flex-col gap-5">
          <div className="glass h-16 rounded-[36px]" />
          <div className="tile h-[330px]" />
        </div>
      </div>
    );
  }

  return (
    <ShellContext.Provider value={value}>
      <div className="flex min-h-screen items-start gap-5 p-5 max-md:px-4 max-md:pb-24">
        <Sidebar account={account} />
        {children}
      </div>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} account={account} />
      {account.kind === "business" ? <CopilotPanel open={copilotOpen} onClose={() => setCopilotOpen(false)} context={copilotContext} /> : null}
      {undo ? <UndoBar undo={undo} onClose={closeUndo} /> : null}
    </ShellContext.Provider>
  );
}
