import { describe, expect, it, vi } from "vitest";

import { runFrameBudgeted } from "./frame-scheduler";

describe("frame-budgeted rendering", () => {
  it("yields between batches instead of monopolising one task", async () => {
    let clock = 0;
    const yieldFrame = vi.fn(async () => { clock += 1; });
    const drawn: number[] = [];

    const completed = await runFrameBudgeted([1, 2, 3, 4, 5], (item) => {
      drawn.push(item);
      clock += 4;
    }, { budgetMs: 10, now: () => clock, yieldFrame });

    expect(completed).toBe(true);
    expect(drawn).toEqual([1, 2, 3, 4, 5]);
    expect(yieldFrame).toHaveBeenCalled();
  });

  it("cancels a stale frame after yielding", async () => {
    let clock = 0;
    let cancelled = false;
    const drawn: number[] = [];

    const completed = await runFrameBudgeted([1, 2, 3, 4], (item) => {
      drawn.push(item);
      clock += 6;
    }, {
      budgetMs: 10,
      now: () => clock,
      yieldFrame: async () => { cancelled = true; },
      cancelled: () => cancelled,
    });

    expect(completed).toBe(false);
    expect(drawn).toEqual([1, 2]);
  });
});
