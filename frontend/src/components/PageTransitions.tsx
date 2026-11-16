"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  createContext,
  startTransition,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  type ComponentProps,
  type ReactNode,
} from "react";

type PendingNavigation = {
  pathname: string;
  finish: () => void;
};

const NavigationContext = createContext<((href: string) => void) | null>(null);

/** Bridge the purchased transition to Next 14 / React 18 without replacing routing. */
export function PageTransitions({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const active = useRef<ViewTransition | null>(null);
  const pending = useRef<PendingNavigation | null>(null);
  const scrollTarget = useRef<string | null>(null);
  const navigationVersion = useRef(0);

  useLayoutEffect(() => {
    if (scrollTarget.current === pathname) {
      // Reset only after the old page has been captured and the new one committed.
      // In particular, do not carry the invoice hero's pinned scroll into results.
      window.scrollTo({ top: 0, left: 0, behavior: "instant" });
      scrollTarget.current = null;
    }

    const navigation = pending.current;
    if (!navigation) return;
    if (navigation.pathname !== pathname) {
      // A browser Back/Forward action can supersede a pending navigation.
      active.current?.skipTransition();
    }
    navigation.finish();
  }, [pathname]);

  useEffect(() => {
    const cancel = () => {
      // skipTransition still runs its update callback. Invalidate it before it
      // can push a destination superseded by Back/Forward or an unmount.
      navigationVersion.current += 1;
      active.current?.skipTransition();
      pending.current?.finish();
      active.current = null;
      scrollTarget.current = null;
    };
    window.addEventListener("popstate", cancel);
    return () => {
      window.removeEventListener("popstate", cancel);
      cancel();
    };
  }, []);

  const navigate = useCallback((href: string) => {
    // One capture at a time. Repeated clicks must not queue stale destinations.
    if (active.current) return;

    scrollTarget.current = null;
    const destination = new URL(href, window.location.href);
    if (
      typeof document.startViewTransition !== "function" ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches ||
      destination.pathname === pathname ||
      destination.hash
    ) {
      router.push(href);
      return;
    }

    const version = ++navigationVersion.current;
    try {
      const transition = document.startViewTransition(() => {
        if (navigationVersion.current !== version) return;
        return new Promise<void>((resolve) => {
          const finish = () => {
            window.clearTimeout(timeout);
            if (pending.current?.finish === finish) pending.current = null;
            resolve();
          };
          // A slow route/network must never leave a frozen snapshot covering the UI.
          const timeout = window.setTimeout(() => {
            transition.skipTransition();
            finish();
          }, 4000);
          pending.current = { pathname: destination.pathname, finish };
          // Keep this target after a snapshot timeout: the route may still arrive.
          scrollTarget.current = destination.pathname;
          startTransition(() => router.push(href, { scroll: false }));
        });
      });
      active.current = transition;
      const cleanup = () => {
        if (active.current === transition) {
          active.current = null;
          pending.current?.finish();
        }
      };
      // ready rejects when snapshots are unavailable (e.g. a background tab).
      void transition.ready.catch(() => undefined);
      void transition.finished.then(cleanup, cleanup);
    } catch {
      navigationVersion.current += 1;
      pending.current?.finish();
      active.current = null;
      scrollTarget.current = null;
      router.push(href);
    }
  }, [pathname, router]);

  return <NavigationContext.Provider value={navigate}>{children}</NavigationContext.Provider>;
}

export function usePageNavigation() {
  const navigate = useContext(NavigationContext);
  if (!navigate) throw new Error("Page navigation requires PageTransitions");
  return navigate;
}

type TransitionLinkProps = Omit<ComponentProps<typeof Link>, "href" | "replace" | "scroll"> & {
  href: string;
};

export function TransitionLink({ href, onClick, ...props }: TransitionLinkProps) {
  const navigate = usePageNavigation();

  return <Link {...props} href={href} onClick={(event) => {
    onClick?.(event);
    if (
      event.defaultPrevented || event.button !== 0 ||
      event.metaKey || event.ctrlKey || event.shiftKey || event.altKey ||
      (event.currentTarget.target && event.currentTarget.target !== "_self") ||
      event.currentTarget.hasAttribute("download")
    ) return;

    const destination = new URL(event.currentTarget.href);
    if (destination.origin !== window.location.origin) return;
    // Keep native anchor navigation and ordinary clicks on the current page.
    if (destination.pathname === window.location.pathname &&
        destination.search === window.location.search) return;

    event.preventDefault();
    navigate(href);
  }} />;
}
