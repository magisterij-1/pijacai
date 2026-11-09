// — navigacija in dostop za posamezne vloge.
// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import type { Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Role, User } from "../src/api/auth";
import { Workspace } from "../src/pages/Workspace";

// Tukaj preverjamo navigacijo; API vedenje vmesnika preverjajo ločeni testi Users.
vi.mock("../src/pages/Users", () => ({ Users: () => null }));
vi.mock("../src/pages/ReceiveMaterials", () => ({ ReceiveMaterials: () => null }));
vi.mock("../src/pages/Stock", () => ({ Stock: () => null }));
vi.mock("../src/pages/Orders", () => ({ Orders: () => null }));
vi.mock("../src/pages/Batches", () => ({ Batches: () => null }));
vi.mock("../src/pages/Traceability", () => ({ Traceability: () => <p>Testni prikaz sledljivosti</p> }));

// Pričakovanja iz US-03–US-15, ne iz konfiguracije navigacije.
const permissions: Record<Role, string[]> = {
  warehouse: ["/prejem-surovin", "/zaloge"],
  planner: ["/nalogi", "/sledljivost"],
  operator: ["/nalogi", "/sarze"],
  quality: ["/kontrola-kakovosti", "/sledljivost"],
  admin: ["/uporabniki"],
};
const pageTitles: Record<string, string> = {
  "/prejem-surovin": "Prejem surovin",
  "/zaloge": "Zaloge",
  "/nalogi": "Proizvodni nalogi",
  "/sarze": "Aktivne šarže",
  "/kontrola-kakovosti": "Šarže za kontrolo",
  "/sledljivost": "Sledljivost",
  "/uporabniki": "Uporabniki",
};
const roles = Object.keys(permissions) as Role[];

let container: HTMLDivElement;
let root: Root;

function user(role: Role): User {
  return { id: 1, name: "Testni uporabnik", email: "test@pijacai.local", role, active: true };
}

function setPath(path: string) {
  window.history.replaceState(null, "", `#${path}`);
}

function render(role: Role, onLogout = vi.fn()) {
  act(() => { root.render(<Workspace user={user(role)} onLogout={onLogout} />); });
}

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  setPath("/");
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  window.history.replaceState(null, "", "/");
});

describe.each(roles)("Navigacija za %s", role => {
  it("prikaže samo dovoljene povezave", () => {
    render(role);
    const links = Array.from(container.querySelectorAll("nav a"), link => link.getAttribute("href"));
    expect(links).toEqual(["#/", ...permissions[role].map(path => `#${path}`)]);
  });

  it.each(Object.entries(pageTitles))("preveri neposredno odprto pot %s", (path, title) => {
    setPath(path);
    render(role);
    const allowed = permissions[role].includes(path);
    expect(container.querySelector("h2")?.textContent).toBe(allowed ? title : "Nimate dostopa");
    if (path === "/sledljivost") expect(container.textContent?.includes("Testni prikaz sledljivosti")).toBe(allowed);
    if (!allowed) {
      expect(container.querySelector(".role-badge")?.textContent).toBe("403");
      expect(container.querySelector(`nav a[href="#${path}"]`)).toBeNull();
    } else {
      expect(container.querySelector(`nav a[href="#${path}"]`)?.getAttribute("aria-current")).toBe("page");
    }
  });

  it("za neznano pot prikaže 404", () => {
    setPath("/neobstojeca-stran");
    render(role);
    expect(container.querySelector("h2")?.textContent).toBe("Stran ni najdena");
    expect(container.querySelector(".role-badge")?.textContent).toBe("404");
  });
});

it("ob spremembi URL iz dovoljene strani preide na zavrnitev dostopa", () => {
  setPath("/uporabniki");
  render("admin");
  expect(container.querySelector("h2")?.textContent).toBe("Uporabniki");
  act(() => {
    setPath("/zaloge");
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
  expect(container.querySelector("h2")?.textContent).toBe("Nimate dostopa");
  expect(document.activeElement).toBe(container.querySelector("h2"));
});

it("ob ponovnem odprtju ohrani zavrnitev nedovoljene poti", () => {
  setPath("/zaloge");
  render("admin");
  expect(container.querySelector("h2")?.textContent).toBe("Nimate dostopa");
  act(() => root.unmount());
  root = createRoot(container);
  render("admin");
  expect(container.querySelector("h2")?.textContent).toBe("Nimate dostopa");
});

it("ob spremembi trenutne vloge ponovno preveri dostop in meni", () => {
  setPath("/sledljivost");
  render("planner");
  expect(container.querySelector("h2")?.textContent).toBe("Sledljivost");
  render("warehouse");
  expect(container.querySelector("h2")?.textContent).toBe("Nimate dostopa");
  expect(container.querySelector('nav a[href="#/sledljivost"]')).toBeNull();
});

it("gumb Odjava pokliče odjavo aplikacije", () => {
  const onLogout = vi.fn();
  render("admin", onLogout);
  act(() => container.querySelector<HTMLButtonElement>("button")!.click());
  expect(onLogout).toHaveBeenCalledOnce();
});
