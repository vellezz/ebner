/**
 * Run something on every page, once per page.
 *
 * With client-side navigation a document is never reloaded, so a script that
 * ran at parse time runs once for the whole session and every page after the
 * first arrives inert. `astro:page-load` fires after the first render and
 * after each navigation, which is the hook these need.
 *
 * The `once` guard is not belt and braces. Depending on how a script is
 * emitted it may itself re-execute on a swap, and then the listener is
 * registered twice and the handler bound twice — a swipe would skip two
 * entries, a vote would be sent twice. Marking the element is what makes it
 * safe to be wrong about which of the two happened.
 */
export function onPage(init: () => void): void {
  document.addEventListener('astro:page-load', init);
}

/** True the first time it is called for this element, false afterwards. */
export function once(element: Element, key: string): boolean {
  const flag = `ready${key}`;
  if ((element as HTMLElement).dataset[flag]) return false;
  (element as HTMLElement).dataset[flag] = '1';
  return true;
}
