import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { cx } from "../../lib/cx";
import styles from "./Toast.module.css";

/** How long a toast stays visible (legacy `ui.js` toast: 3400 ms). */
export const TOAST_MS = 3400;

type ShowToast = (text: string) => void;

const ToastContext = createContext<ShowToast | null>(null);

/** Single bottom-right status toast, as in the prototype; a new message replaces the current one. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [text, setText] = useState("");
  const [visible, setVisible] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const show = useCallback<ShowToast>((message) => {
    setText(message);
    setVisible(true);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      setVisible(false);
    }, TOAST_MS);
  }, []);

  useEffect(
    () => () => {
      clearTimeout(timer.current);
    },
    [],
  );

  const value = useMemo(() => show, [show]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        role="status"
        aria-live="polite"
        className={cx(styles.toast, visible && styles.on)}
      >
        {visible ? text : ""}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ShowToast {
  const show = useContext(ToastContext);
  if (!show) throw new Error("useToast must be used inside <ToastProvider>");
  return show;
}
