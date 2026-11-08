import { useEffect, useRef, useState } from "react";
import type { User } from "../api/auth";
import { canAccess, pages, readPagePath } from "../navigation";
import { RoleHome } from "./RoleHome";
import { Users } from "./Users";
import { ReceiveMaterials } from "./ReceiveMaterials";

export function Workspace({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [path, setPath] = useState(readPagePath);
  const heading = useRef<HTMLHeadingElement>(null);
  const page = pages.find(item => item.path === path);
  const allowedPages = pages.filter(item => canAccess(item, user.role));
  const denied = page !== undefined && !canAccess(page, user.role);

  useEffect(() => {
    const onHashChange = () => setPath(readPagePath());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => { heading.current?.focus(); }, [path, user.role]);

  return (
    <>
      <div className="workspace-header">
        <p className="muted">{user.name}</p>
        <button className="secondary" onClick={onLogout}>Odjava</button>
      </div>
      <nav aria-label="Glavna navigacija">
        <a href="#/" aria-current={path === "/" ? "page" : undefined}>Začetna stran</a>
        {allowedPages.map(item => (
          <a key={item.path} href={`#${item.path}`} aria-current={path === item.path ? "page" : undefined}>
            {item.title}
          </a>
        ))}
      </nav>
      {path === "/" ? <RoleHome user={user} /> : denied ? (
        <section aria-labelledby="page-title">
          <p className="role-badge">403</p>
          <h2 id="page-title" ref={heading} tabIndex={-1}>Nimate dostopa</h2>
          <p>Vaša vloga ne dovoljuje dostopa do te strani.</p>
          <a href="#/">Nazaj na začetno stran</a>
        </section>
      ) : page ? (
        <section aria-labelledby="page-title">
          <h2 id="page-title" ref={heading} tabIndex={-1}>{page.title}</h2>
          <p className="muted">{page.description}</p>
          {page.path === "/uporabniki" && <Users currentUserId={user.id} onSelfDeactivated={onLogout} />}
          {page.path === "/prejem-surovin" && <ReceiveMaterials />}
        </section>
      ) : (
        <section aria-labelledby="page-title">
          <p className="role-badge">404</p>
          <h2 id="page-title" ref={heading} tabIndex={-1}>Stran ni najdena</h2>
          <a href="#/">Nazaj na začetno stran</a>
        </section>
      )}
    </>
  );
}
