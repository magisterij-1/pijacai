// — začetni prikaz glede na uporabniško vlogo.
import { useEffect, useRef } from "react";
import type { Role, User } from "../api/auth";

const roleViews: Record<Role, { label: string; title: string; description: string }> = {
  warehouse: {
    label: "Skladiščnik",
    title: "Skladišče",
    description: "Delovno okolje za prejem surovin in embalaže ter pregled zalog.",
  },
  planner: {
    label: "Planer",
    title: "Načrtovanje proizvodnje",
    description: "Delovno okolje za proizvodne naloge in pregled sledljivosti.",
  },
  operator: {
    label: "Operater",
    title: "Proizvodnja",
    description: "Delovno okolje za zagon šarž in zaključek polnjenja.",
  },
  quality: {
    label: "Kontrolor kakovosti",
    title: "Kontrola kakovosti",
    description: "Delovno okolje za meritve kakovosti in odločanje o šaržah.",
  },
  admin: {
    label: "Administrator",
    title: "Upravljanje uporabnikov",
    description: "Delovno okolje za upravljanje uporabniških računov.",
  },
};

export function RoleHome({ user }: { user: User }) {
  const heading = useRef<HTMLHeadingElement>(null);
  const view = roleViews[user.role];

  useEffect(() => { heading.current?.focus(); }, []);

  return (
    <section aria-labelledby="home-title">
      <p className="role-badge">{view.label}</p>
      <h2 id="home-title" ref={heading} tabIndex={-1}>{view.title}</h2>
      <p>Dobrodošli, {user.name}.</p>
      <p className="muted">{view.description}</p>
    </section>
  );
}
