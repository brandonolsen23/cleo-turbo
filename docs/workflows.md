# Cleo Turbo — Workflows & Problems to Solve

> North star document. Describes the real-world workflows Cleo is being built to centralize and
> automate. Each section captures a current process, its pain points, and what "solved" looks like.
>
> This document survives any app rebuild. It's the "why" behind the system.
>
> **Core goal:** Centralize and automate. Remove friction. Capture workflow automatically.
> Stop switching between disconnected tools. Make it easy to track work without extra effort.

---

## 1. The Prospecting Loop

The daily cycle of finding property owners and making contact. Currently 8 manual steps
bouncing between GeoWarehouse, Realtrack, Google, LinkedIn, Canada411, HubSpot, Outlook,
Productive.ai, and Google Earth.

### Current Process

**Step 1: Pick a target (city or brand → find a property)**
- Choose a city/market OR a brand category
- Zoom into the area, look for neighbourhood plazas, retail nodes
- Find a plaza that hasn't been worked yet

**Step 2: Research the parcel (GeoWarehouse)**
- Look up the parcel in GeoWarehouse
- A parcel may contain one building with one tenant, or multiple buildings with many tenants
- Grab everything: owner name, purchase price, site size, corp mailing address, PIN, ARN
- Understanding the PARCEL is critical — a Starbucks pin means nothing without knowing if it's a standalone pad or the corner of a 100,000 SF retail centre. The parcel is what transfers and is what's owned.

**Step 3: Find the transaction (Realtrack)**
- If the GeoWarehouse sale date is 1996 or newer, search the address in Realtrack
- Learn as much as possible from the RT data
- Key target: contact name and phone number for the buyer

**Step 4: Size up the owner's portfolio (Realtrack)**
- Search the contact NAME across ALL asset classes (not just retail — industrial, residential, everything)
- Search the CORP NAME across all asset classes
- Want the full picture of how many properties they own
- Portfolio size determines the outreach approach

**Step 5: Find contact info (multi-channel dig)**
- Try the RT phone number first (often outdated, especially older records)
- Google search: "firstname lastname city" using the city from the corporate address
- This brings up a LinkedIn profile ~40-50% of the time
- If the LinkedIn profile looks real-estate-related, use Datanyze extension to find email or cell phone
- If no LinkedIn hit: check if the corporate address is residential
  - Verify by Googling the corp address
  - Search Canada411 for a home phone at that address
  - Search GeoWarehouse for who owns that residential property (confirms the contact)
  - Sometimes reveals if owner has passed (obituary + family member on title at home address)
- Last resort: find them on Facebook, send cold message

**Step 6: Make contact**
- Priority order: Call → Email → Letter
- If phone found → call immediately
- If email only → send via Outlook (HubSpot auto-tracks)
- If residential corp address confirmed → send a physical letter
- All calls recorded by Productive.ai → summaries auto-sent to HubSpot

**Step 7: Log and track**
- Currently logs on Google Earth pins (disconnected from CRM)
- HubSpot tracks emails automatically
- Productive.ai tracks calls automatically
- NO unified view of outreach status per owner across all their properties
- Wants: "owner was contacted about Property X" shown on all their other properties
- Wants: drip campaigns (email → 1 week nudge → 2 week nudge → 1 week final)
- Wants: outreach type tracking (call/email/letter) with outcomes

**Step 8: Repeat**
- Find next unworked property → same loop

### Pain Points

- **Tool switching:** GeoWarehouse → Realtrack → Google → LinkedIn → Canada411 → HubSpot → Outlook, every single time
- **No memory across properties:** Contact an owner about one property, their other 15 properties show no record of it
- **Manual portfolio discovery:** Have to search contact name and corp name separately across all asset classes
- **Disconnected tracking:** Google Earth pins, HubSpot emails, Productive.ai calls — three systems, no unified view
- **No "unworked" tracking:** No way to see which properties/owners in an area haven't been touched yet
- **Stale contact info:** RT phone numbers are often decades old, no systematic way to flag or update

### What "Solved" Looks Like

- Steps 1-4 are pre-computed: properties already linked to transactions, owners, portfolios, and parcels
- Step 5 is partially pre-filled from RT data; enrichment fields (email, LinkedIn) persist in CRM
- Steps 6-7 are tracked in one place with automatic capture (HubSpot sync, call logging)
- Step 8 is a filter: "show me unworked properties in this area" is a one-click query
- Contacting an owner about one property automatically reflects on all their properties
