import { add } from "@monorepo-pnpm/lib-a";

export function addThree(a: number, b: number, c: number): number {
  return add(add(a, b), c);
}
