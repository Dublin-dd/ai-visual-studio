/** Serial latest-snapshot writer. Never lets an older save overwrite a newer one.
 * flush() waits for all pending revisions; failures keep the latest snapshot retryable.
 */
export function createSaveQueue<T>(write: (value: T) => Promise<unknown>) {
  let revision = 0;
  let savedRevision = 0;
  let latest: T;
  let running: Promise<void> | null = null;
  return {
    set(value: T) { latest = value; revision += 1; },
    get dirty() { return savedRevision < revision; },
    flush(): Promise<void> {
      if (running) return running;
      running = (async () => {
        while (savedRevision < revision) {
          const current = revision;
          const value = latest;
          await write(value);
          savedRevision = current;
        }
      })().finally(() => { running = null; });
      return running;
    },
  };
}
