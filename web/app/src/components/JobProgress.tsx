import { motion } from "framer-motion";

export default function JobProgress({
  progress,
  message,
}: {
  progress: number;
  message: string;
}) {
  return (
    <div className="w-full">
      <div className="mb-2 flex items-center justify-between font-mono text-xs text-ink-soft">
        <span>{message || "working…"}</span>
        <span className="text-ink-faint">{Math.round(progress * 100)}%</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
        <motion.div
          className="h-full rounded-full"
          style={{
            background:
              "linear-gradient(90deg, var(--color-accent), var(--color-accent-bright))",
          }}
          animate={{ width: `${Math.max(4, progress * 100)}%` }}
          transition={{ ease: [0.16, 1, 0.3, 1], duration: 0.4 }}
        />
      </div>
    </div>
  );
}
