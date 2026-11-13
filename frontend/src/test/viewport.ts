/** jsdom has no `matchMedia`; this stub evaluates `(max-width: Npx)` against a settable width. */
let width = 1440;
const listeners = new Set<() => void>();

export function setViewportWidth(next: number): void {
  width = next;
  for (const listener of listeners) listener();
}

export function installMatchMedia(): void {
  window.matchMedia = (query: string): MediaQueryList => {
    const max = /\(max-width:\s*(\d+)px\)/.exec(query);
    const matches = max?.[1] ? width <= Number(max[1]) : false;
    const add = (_type: string, listener: () => void) => {
      listeners.add(listener);
    };
    const remove = (_type: string, listener: () => void) => {
      listeners.delete(listener);
    };
    return {
      matches,
      media: query,
      onchange: null,
      addEventListener: add,
      removeEventListener: remove,
      addListener: (l: () => void) => {
        listeners.add(l);
      },
      removeListener: (l: () => void) => {
        listeners.delete(l);
      },
      dispatchEvent: () => false,
    } as unknown as MediaQueryList;
  };
}
