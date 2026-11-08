// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import type { Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { User } from "../src/api/auth";
import { createUser, deactivateUser, listUsers, UserApiError } from "../src/api/users";
import { Users } from "../src/pages/Users";

vi.mock("../src/api/users", async importOriginal => {
  const actual = await importOriginal<typeof import("../src/api/users")>();
  return { ...actual, listUsers: vi.fn(), createUser: vi.fn(), deactivateUser: vi.fn() };
});

const admin: User = { id: 1, name: "Administrator", email: "admin@pijacai.local", role: "admin", active: true };
const operator: User = { id: 2, name: "Operater", email: "operator@pijacai.local", role: "operator", active: true };
let container: HTMLDivElement;
let root: Root;
let onSelfDeactivated: ReturnType<typeof vi.fn>;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  vi.mocked(listUsers).mockReset().mockResolvedValue([admin, operator]);
  vi.mocked(createUser).mockReset();
  vi.mocked(deactivateUser).mockReset();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  onSelfDeactivated = vi.fn();
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

async function render() {
  await act(async () => {
    root.render(<Users currentUserId={1} onSelfDeactivated={onSelfDeactivated} />);
  });
}

function fill(name: string, value: string) {
  const input = container.querySelector<HTMLInputElement>(`input[name="${name}"]`)!;
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

function fillForm(password = "TestnoGeslo2026!") {
  fill("name", "Planer");
  fill("email", "planner@pijacai.local");
  fill("password", password);
  act(() => {
    const select = container.querySelector("select")!;
    select.value = "planner";
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

async function submit() {
  await act(async () => {
    container.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
}

function deactivateButton(id: number): HTMLButtonElement {
  const email = id === 1 ? admin.email : operator.email;
  const row = Array.from(container.querySelectorAll("tbody tr")).find(item => item.textContent?.includes(email))!;
  return row.querySelector("button")!;
}

it("prikaže uporabnike in stanje neaktivnega računa brez gumba za deaktivacijo", async () => {
  vi.mocked(listUsers).mockResolvedValue([admin, { ...operator, active: false }]);
  await render();
  const rows = container.querySelectorAll("tbody tr");
  expect(rows.length).toBe(2);
  expect(rows[1].textContent).toContain("Neaktiven");
  expect(rows[1].querySelector("button")).toBeNull();
  expect(rows[0].textContent).toContain("(vi)");
});

it("ustvari račun z izbrano vlogo, dopolni seznam in počisti geslo", async () => {
  const created: User = { id: 3, name: "Planer", email: "planner@pijacai.local", role: "planner", active: true };
  vi.mocked(createUser).mockResolvedValue(created);
  await render();
  fillForm();
  await submit();
  expect(createUser).toHaveBeenCalledWith({
    name: "Planer", email: "planner@pijacai.local", password: "TestnoGeslo2026!", role: "planner",
  });
  expect(container.querySelectorAll("tbody tr").length).toBe(3);
  expect(container.textContent).toContain("Uporabnik je ustvarjen.");
  expect(container.querySelector<HTMLInputElement>('[name="password"]')!.value).toBe("");
});

it("prikaže podvojeno e-pošto ob polju in počisti geslo", async () => {
  const message = "Uporabnik s to e-pošto že obstaja.";
  vi.mocked(createUser).mockRejectedValue(new UserApiError(message, { email: message }));
  await render();
  fillForm();
  await submit();
  expect(container.querySelector("#user-email-error")?.textContent).toBe(message);
  expect(container.querySelector<HTMLInputElement>('[name="password"]')!.value).toBe("");
  expect(container.querySelectorAll("tbody tr").length).toBe(2);
});

it.each(["1234567", "č".repeat(37)])("zavrne neveljavno geslo pred API klicem: %s", async password => {
  await render();
  fillForm(password);
  await submit();
  expect(createUser).not.toHaveBeenCalled();
  expect(container.querySelector("#user-password-error")).not.toBeNull();
});

it("ob potrjeni deaktivaciji ohrani vrstico in spremeni stanje", async () => {
  vi.mocked(deactivateUser).mockResolvedValue({ ...operator, active: false });
  await render();
  await act(async () => deactivateButton(2).click());
  expect(deactivateUser).toHaveBeenCalledWith(2);
  const row = container.querySelectorAll("tbody tr")[1];
  expect(row.textContent).toContain("Neaktiven");
  expect(row.querySelector("button")).toBeNull();
  expect(onSelfDeactivated).not.toHaveBeenCalled();
});

it("preklic potrditve ne pošlje zahteve", async () => {
  vi.mocked(window.confirm).mockReturnValue(false);
  await render();
  await act(async () => deactivateButton(2).click());
  expect(deactivateUser).not.toHaveBeenCalled();
});

it("po samodeaktivaciji sproži odjavo", async () => {
  vi.mocked(deactivateUser).mockResolvedValue({ ...admin, active: false });
  await render();
  await act(async () => deactivateButton(1).click());
  expect(deactivateUser).toHaveBeenCalledWith(1);
  expect(onSelfDeactivated).toHaveBeenCalledOnce();
});

it("prikaže napako nalaganja in omogoči ponoven poskus", async () => {
  vi.mocked(listUsers).mockRejectedValueOnce(new Error("Povezava s strežnikom ni uspela."));
  await render();
  expect(container.textContent).toContain("Povezava s strežnikom ni uspela.");
  const refresh = Array.from(container.querySelectorAll("button")).find(item => item.textContent === "Osveži seznam")!;
  await act(async () => refresh.click());
  expect(container.querySelectorAll("tbody tr").length).toBe(2);
});
