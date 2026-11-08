import { describe, expect, it } from "vitest";
import { createSaveQueue } from "./save-queue";

describe("画布保存顺序", () => {
  it("导出等待正在保存的旧快照和随后到达的最新快照", async () => {
    const writes: number[] = [];
    let release!: () => void;
    const gate = new Promise<void>(resolve => { release = resolve; });
    const queue = createSaveQueue(async (n: number) => { writes.push(n); if (n === 1) await gate; });
    queue.set(1);
    const first = queue.flush();
    queue.set(2);
    queue.set(3);
    const exportSave = queue.flush();
    expect(exportSave).toBe(first);
    expect(writes).toEqual([1]);
    release();
    await exportSave;
    expect(writes).toEqual([1, 3]);
    expect(queue.dirty).toBe(false);
  });
  it("失败不标记已保存，再试写入最新草稿", async () => {
    let fail = true;
    const writes: string[] = [];
    const queue = createSaveQueue(async (s: string) => { if (fail) throw Error("offline"); writes.push(s); });
    queue.set("first");
    await expect(queue.flush()).rejects.toThrow("offline");
    expect(queue.dirty).toBe(true);
    queue.set("latest");
    fail = false;
    await queue.flush();
    expect(writes).toEqual(["latest"]);
    expect(queue.dirty).toBe(false);
  });
});
