// A draft not yet saved is asked about before it goes (plan M1 9.8, Paket 9c2 K8; after the old app's
// leaveGuard.ts): by a question in the page for a move inside the app, and by the browser's own for closing
// the tab or reloading, the only way a page may ask there. Which moves of the same route take the draft
// along is the page's to say (`goesWith`): on the tree page another row does, another page of the source
// does not.
import { computed, onBeforeUnmount, onMounted, ref, toValue, type MaybeRefOrGetter } from "vue";
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRouter, type RouteLocationNormalized } from "vue-router";

// What the browser's question is given in the old way, where a page set a text of its own: any text but
// none makes it ask; the words are the browser's.
const ASK = "draft";

export interface LeaveGuardOptions {
  /** A move within the route that takes the draft along; by default one to another path. */
  goesWith?: (to: RouteLocationNormalized, from: RouteLocationNormalized) => boolean;
}

interface Question {
  to: RouteLocationNormalized;
  answer: (leave: boolean) => void;
}

/** Ask before a move leaves the `dirty` draft. Returns whether the page is asking, and where its answer goes. */
export function useLeaveGuard(dirty: MaybeRefOrGetter<boolean>, options: LeaveGuardOptions = {}) {
  const router = useRouter();
  const goesWith = options.goesWith ?? ((to, from) => to.path !== from.path);
  const question = ref<Question | null>(null);
  // A second move while the question is open - a second press of the browser's back, say - is refused:
  // asked about as well, it took the question's place and the first hung unanswered. The router takes the
  // refused move for the newest all the same and cancels the one asked about, whatever its answer: a leave
  // confirmed then is made anew, and passes unasked.
  let overtaken = false;
  let released = false;

  function guard(to: RouteLocationNormalized): boolean | Promise<boolean> {
    if (released || !toValue(dirty)) return true;
    if (question.value) {
      overtaken = true;
      return false;
    }
    return new Promise<boolean>((resolve) => {
      question.value = { to, answer: resolve };
    });
  }

  onBeforeRouteLeave(guard);
  onBeforeRouteUpdate((to, from) => {
    if (question.value) {
      overtaken = true;
      return false;
    }
    return goesWith(to, from) ? guard(to) : true;
  });

  /** The answer to the page's question: leave, or stay with the draft. */
  function answer(leave: boolean): void {
    const asked = question.value;
    if (!asked) return;
    question.value = null;
    asked.answer(leave);
    if (leave && overtaken) leaveAnew(asked.to);
    overtaken = false;
  }

  // Where a back already moved the browser's history, the page follows it there; a link asked about is
  // followed as a link is.
  function leaveAnew(to: RouteLocationNormalized): void {
    released = true;
    const there = router.options.history.location === to.fullPath;
    void (there ? router.replace(to.fullPath) : router.push(to.fullPath)).finally(() => {
      released = false;
    });
  }

  function warnBeforeUnload(event: BeforeUnloadEvent): void {
    if (!toValue(dirty)) return;
    event.preventDefault();
    // the old way some browsers still ask for
    event.returnValue = ASK;
  }

  onMounted(() => window.addEventListener("beforeunload", warnBeforeUnload));
  onBeforeUnmount(() => window.removeEventListener("beforeunload", warnBeforeUnload));

  const leaving = computed(() => question.value !== null);
  return { leaving, answer };
}
