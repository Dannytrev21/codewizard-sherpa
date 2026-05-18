import express from "express";
import { add } from "@monorepo-pnpm/lib-a";
import { addThree } from "@monorepo-pnpm/lib-b";

const app = express();

app.get("/", (_req, res) => {
  res.json({ sum: add(1, 2), triple: addThree(1, 2, 3) });
});

app.listen(3000);
