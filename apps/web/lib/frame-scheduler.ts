export type FrameSchedulerOptions = {
  budgetMs?: number;
  now?: () => number;
  yieldFrame?: () => Promise<void>;
  cancelled?: () => boolean;
};

const nextAnimationFrame = () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));

export async function runFrameBudgeted<T>(
  items: readonly T[],
  draw: (item: T, index: number) => void,
  options: FrameSchedulerOptions = {},
): Promise<boolean> {
  const budgetMs = options.budgetMs ?? 10;
  const now = options.now ?? (() => performance.now());
  const yieldFrame = options.yieldFrame ?? nextAnimationFrame;
  const cancelled = options.cancelled ?? (() => false);
  let sliceStarted = now();

  for (let index = 0; index < items.length; index += 1) {
    if (cancelled()) return false;
    draw(items[index], index);
    if (now() - sliceStarted >= budgetMs && index + 1 < items.length) {
      await yieldFrame();
      if (cancelled()) return false;
      sliceStarted = now();
    }
  }
  return !cancelled();
}
