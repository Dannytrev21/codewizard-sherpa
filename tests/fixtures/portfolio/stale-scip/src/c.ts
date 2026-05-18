import { plusAnswer } from "./b";

export function tripleAnswer(x: number): number {
  return plusAnswer(plusAnswer(plusAnswer(x)));
}
