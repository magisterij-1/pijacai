import type { Role } from "./api/auth";

export type Page = {
  path: string;
  title: string;
  roles: readonly Role[];
  description: string;
};

// Skupna pravila za prikaz menija in dostop pri neposrednem odpiranju poti.
export const pages: readonly Page[] = [
  {
    path: "/prejem-surovin", title: "Prejem surovin", roles: ["warehouse"],
    description: "Evidentiranje prejetih surovin in embalaže.",
  },
  {
    path: "/zaloge", title: "Zaloge", roles: ["warehouse"],
    description: "Pregled zalog surovin in embalaže po serijah.",
  },
  {
    path: "/nalogi", title: "Proizvodni nalogi", roles: ["planner", "operator"],
    description: "Pregled proizvodnih nalogov.",
  },
  {
    path: "/sarze", title: "Aktivne šarže", roles: ["operator"],
    description: "Pregled proizvodnih šarž in zaključek polnjenja.",
  },
  {
    path: "/kontrola-kakovosti", title: "Šarže za kontrolo", roles: ["quality"],
    description: "Meritve kakovosti in odločanje o šaržah.",
  },
  {
    path: "/sledljivost", title: "Sledljivost", roles: ["planner", "quality"],
    description: "Povezave med šaržami in uporabljenimi serijami surovin.",
  },
  {
    path: "/uporabniki", title: "Uporabniki", roles: ["admin"],
    description: "Upravljanje uporabniških računov in njihovih vlog.",
  },
];

export function canAccess(page: Page, role: Role): boolean {
  return page.roles.includes(role);
}

export function readPagePath(): string {
  const path = window.location.hash.slice(1);
  return path.replace(/\/+$/, "") || "/";
}
