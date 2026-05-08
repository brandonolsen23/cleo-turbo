import { useLocation } from "react-router-dom";
import type { AIPageContext } from "../../types";

const ROUTE_PATTERNS: { regex: RegExp; entity_type: AIPageContext["entity_type"] }[] = [
  { regex: /^\/properties\/([^/?#]+)/,    entity_type: "property"    },
  { regex: /^\/contacts\/([^/?#]+)/,      entity_type: "contact"     },
  { regex: /^\/groups\/([^/?#]+)/,        entity_type: "group"       },
  { regex: /^\/deals\/([^/?#]+)/,         entity_type: "deal"        },
  { regex: /^\/lists\/([^/?#]+)/,         entity_type: "list"        },
  { regex: /^\/transactions\/([^/?#]+)/,  entity_type: "transaction" },
];

/** Read the current pathname and, if it matches a known entity-detail
 * route, return the matching AIPageContext. Otherwise null. */
export function usePageContext(): AIPageContext | null {
  const { pathname } = useLocation();
  for (const { regex, entity_type } of ROUTE_PATTERNS) {
    const m = pathname.match(regex);
    if (m && m[1]) return { entity_type, id: m[1] };
  }
  return null;
}
