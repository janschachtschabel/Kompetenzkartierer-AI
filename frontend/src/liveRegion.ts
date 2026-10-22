const NBSP = " ";

/**
 * What a live region is to hold next so that `message` is read out. The same
 * message as the one it holds would leave it unchanged, and a screen reader
 * would say nothing: it gets a no-break space the eye does not see, which the
 * next repeat takes off again. Emptying the region first in the same task
 * does not do: the browser reports a region's change between tasks, and
 * sees the same text (recheck R3-1).
 */
export function sayAnew(current: string, message: string): string {
  if (!message || current.replace(/ $/, "") !== message) return message;
  return current.endsWith(NBSP) ? message : message + NBSP;
}
