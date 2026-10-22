// The api is one module to the app: tests replace its functions here
// (vi.spyOn), so the pages import from "@/api" and never from its files
// (eslint.config.js enforces it).
export * from "./account";
export * from "./http";
