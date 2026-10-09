import { experiments } from "../api/client";

export function csvValidationError(file: File): string | null {
  if (!/\.csv$/i.test(file.name)) return "Choose a CSV file.";
  if (file.size > 10 * 1024 * 1024) return "CSV files must be 10 MB or smaller.";
  return null;
}

function minimumUploadDisplay(signal: AbortSignal) {
  return new Promise<void>(resolve => {
    const finish = () => {
      window.clearTimeout(timer);
      signal.removeEventListener("abort", finish);
      resolve();
    };
    const timer = window.setTimeout(finish, 3000);
    signal.addEventListener("abort", finish, { once: true });
    if (signal.aborted) finish();
  });
}

/** Registration and its visible uploading state finish together; cancellation skips the delay. */
export async function uploadCsv(file: File, signal: AbortSignal, folderId?: string | null) {
  const invalid = csvValidationError(file);
  if (invalid) throw new Error(invalid);
  signal.throwIfAborted();
  const minimumDisplay = minimumUploadDisplay(signal);
  try {
    const result = await experiments.upload(file, signal, folderId);
    await minimumDisplay;
    signal.throwIfAborted();
    return result;
  } catch (error) {
    await minimumDisplay;
    signal.throwIfAborted();
    throw error;
  }
}
