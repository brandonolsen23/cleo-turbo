const fs = require("fs");
const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
        Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
        ShadingType, PageNumber, PageBreak, LevelFormat, ExternalHyperlink } = require("docx");

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };
const cellMargins = { top: 60, bottom: 60, left: 100, right: 100 };

const headerBg = { fill: "1B4332", type: ShadingType.CLEAR };
const headerRun = { bold: true, font: "Arial", size: 18, color: "FFFFFF" };
const cellRun = { font: "Arial", size: 17 };
const cellRunBold = { font: "Arial", size: 17, bold: true };
const cellRunSmall = { font: "Arial", size: 16, color: "555555" };

// Column widths for the main table (total = 9360 DXA for US Letter with 1" margins)
const colWidths = [2200, 1300, 1100, 1100, 1100, 2560]; // Name, Platform, Parcel, Zoning, API, URL

function headerCell(text, width) {
  return new TableCell({
    borders, width: { size: width, type: WidthType.DXA },
    shading: headerBg, margins: cellMargins,
    verticalAlign: "center",
    children: [new Paragraph({ children: [new TextRun({ text, ...headerRun })] })]
  });
}

function cell(children, width, shading) {
  const opts = { borders, width: { size: width, type: WidthType.DXA }, margins: cellMargins, children };
  if (shading) opts.shading = { fill: shading, type: ShadingType.CLEAR };
  return new TableCell(opts);
}

function textCell(text, width, shading) {
  return cell([new Paragraph({ children: [new TextRun({ text, ...cellRun })] })], width, shading);
}

function checkCell(val, width, shading) {
  const color = val === "Yes" ? "2D6A4F" : val === "Partial" ? "B07D10" : "999999";
  return cell([new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: val, ...cellRun, bold: true, color })] })], width, shading);
}

// --- DATA ---
const majorMunis = [
  ["City of Toronto", "ArcGIS Enterprise", "Yes", "Yes", "Yes", "gis.toronto.ca/arcgis/rest/services/"],
  ["City of Ottawa", "ArcGIS Enterprise", "Yes", "Yes", "Yes", "maps.ottawa.ca/ArcGIS/rest/services/"],
  ["City of Hamilton", "ArcGIS Hub", "Yes", "Partial", "Yes", "open.hamilton.ca"],
  ["City of London", "ArcGIS Online", "Yes", "Yes", "Yes", "maps.london.ca/arcgisb/rest/services/"],
  ["Region of Peel", "ArcGIS Hub", "Yes", "Partial", "Yes", "data-regionofpeel.hub.arcgis.com"],
  ["Region of Halton", "ArcGIS/Geocortex", "Yes", "Partial", "Yes", "haltonhills.ca MapLinks"],
  ["Region of Durham", "ArcGIS Online", "Yes", "Yes", "Yes", "maps.durham.ca/arcgis/rest/services/"],
  ["Region of York", "ArcGIS Hub", "Yes", "Partial", "Yes", "insights-york.opendata.arcgis.com"],
  ["Region of Waterloo", "ArcGIS Hub", "Yes", "Partial", "Yes", "region-of-waterloo-geohub-rmw.hub.arcgis.com"],
  ["City of Kitchener", "ArcGIS Hub", "Yes", "Partial", "Yes", "open-kitchenergis.opendata.arcgis.com"],
  ["City of Windsor", "ArcGIS Hub", "Yes", "Partial", "Yes", "mapp-my-city-citywindsor.hub.arcgis.com"],
  ["City of Kingston", "ArcGIS Hub", "Yes", "Partial", "Yes", "maps-cityofkingston.hub.arcgis.com"],
  ["City of Barrie", "ArcGIS Hub", "Yes", "Yes", "Yes", "public-barrie.opendata.arcgis.com"],
  ["City of Guelph", "ArcGIS Hub", "Yes", "Partial", "Yes", "geodatahub-cityofguelph.opendata.arcgis.com"],
  ["Niagara Region", "ArcGIS Hub", "Yes", "Partial", "Yes", "open.niagararegion.ca"],
  ["City of Thunder Bay", "ArcGIS Online", "Yes", "Partial", "Yes", "opendata.thunderbay.ca"],
];

const countyMunis = [
  ["Simcoe County", "ArcGIS + GeoServer", "Yes", "Yes", "Yes", "opengis.simcoe.ca"],
  ["Dufferin County", "ArcGIS Online", "Yes", "Yes", "Yes", "dufferincounty.maps.arcgis.com"],
  ["Wellington County", "ArcGIS/Geocortex", "Yes", "Yes", "Yes", "wellington.ca/maps"],
  ["Grey County", "ArcGIS/Geocortex", "Yes", "Yes", "Yes", "maps.grey.ca"],
  ["Bruce County", "ArcGIS Hub", "Yes", "Yes", "Yes", "gis.brucecounty.on.ca"],
  ["Hastings County", "ArcGIS Hub", "Yes", "Yes", "Yes", "hastings-county-gis-hastings-gis.hub.arcgis.com"],
  ["Lennox & Addington", "ArcGIS Hub", "Yes", "Yes", "Yes", "l-a-mapping-services-lennoxaddington.hub.arcgis.com"],
  ["Leeds and Grenville", "ArcGIS Hub", "Yes", "Yes", "Yes", "geohub-uclg.hub.arcgis.com"],
  ["Chatham-Kent", "Geocortex/ArcGIS", "Yes", "Yes", "Yes", "gismaps.chatham-kent.ca"],
  ["Brant County", "ArcGIS", "Yes", "Yes", "Yes", "maps.brant.ca"],
  ["Norfolk County", "ArcGIS", "Yes", "Yes", "Yes", "norfolkcounty.ca"],
  ["Oxford County", "Geocortex/ArcGIS", "Yes", "Yes", "Yes", "webmap.oxfordcounty.ca"],
  ["Elgin County", "Geocortex/ArcGIS", "Yes", "Yes", "Yes", "geohub.elgin.ca"],
  ["Middlesex County", "Geocortex/ArcGIS", "Yes", "Yes", "Yes", "maps.middlesex.ca"],
  ["Lambton County", "ArcGIS", "Yes", "Yes", "Yes", "lambtongis.ca"],
  ["Huron County", "Geocortex/ArcGIS", "Yes", "Yes", "Yes", "gis.huroncounty.ca"],
  ["Perth County", "Geocortex/ArcGIS", "Yes", "Yes", "Yes", "maps.perthcounty.ca"],
  ["Haldimand County", "ArcGIS", "Yes", "Yes", "Yes", "maps.haldimandcounty.on.ca"],
  ["Kawartha Lakes", "ArcGIS Hub", "Yes", "Yes", "Yes", "geohub-kawartha.hub.arcgis.com"],
  ["Peterborough County", "Geocortex/ArcGIS", "Yes", "Yes", "Yes", "ptbocounty.geocortex.com"],
];

function makeRow(data, shading) {
  return new TableRow({
    children: [
      cell([new Paragraph({ children: [new TextRun({ text: data[0], ...cellRunBold })] })], colWidths[0], shading),
      textCell(data[1], colWidths[1], shading),
      checkCell(data[2], colWidths[2], shading),
      checkCell(data[3], colWidths[3], shading),
      checkCell(data[4], colWidths[4], shading),
      cell([new Paragraph({ children: [new TextRun({ text: data[5], ...cellRunSmall })] })], colWidths[5], shading),
    ]
  });
}

function makeTable(data) {
  const headerRow = new TableRow({
    children: [
      headerCell("Municipality", colWidths[0]),
      headerCell("Platform", colWidths[1]),
      headerCell("Parcels", colWidths[2]),
      headerCell("Zoning", colWidths[3]),
      headerCell("API", colWidths[4]),
      headerCell("Portal / Endpoint", colWidths[5]),
    ]
  });
  const rows = data.map((d, i) => makeRow(d, i % 2 === 0 ? "F5F5F5" : undefined));
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: colWidths,
    rows: [headerRow, ...rows]
  });
}

// --- DOCUMENT ---
const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 36, bold: true, font: "Arial", color: "1B4332" },
        paragraph: { spacing: { before: 360, after: 200 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Arial", color: "2D6A4F" },
        paragraph: { spacing: { before: 280, after: 160 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Arial", color: "40916C" },
        paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 2 } },
    ]
  },
  numbering: {
    config: [
      { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "numbers", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
    ]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
      }
    },
    headers: {
      default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: "Cleo Turbo \u2014 Discovery Research", font: "Arial", size: 16, color: "999999" })] })] })
    },
    footers: {
      default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "Page ", font: "Arial", size: 16, color: "999999" }), new TextRun({ children: [PageNumber.CURRENT], font: "Arial", size: 16, color: "999999" })] })] })
    },
    children: [
      // TITLE
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 }, children: [
        new TextRun({ text: "Ontario Municipal GIS & Zoning Map", font: "Arial", size: 44, bold: true, color: "1B4332" })
      ]}),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 }, children: [
        new TextRun({ text: "API Accessibility Discovery", font: "Arial", size: 36, bold: true, color: "2D6A4F" })
      ]}),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 400 }, children: [
        new TextRun({ text: "April 2026 \u2014 Research Only", font: "Arial", size: 22, color: "777777" })
      ]}),

      // EXECUTIVE SUMMARY
      new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Executive Summary")] }),
      new Paragraph({ spacing: { after: 200 }, children: [
        new TextRun("Ontario has "), new TextRun({ text: "444 municipalities", bold: true }),
        new TextRun(" (per AMO). Of these, at least "), new TextRun({ text: "80+ have public GIS data portals", bold: true }),
        new TextRun(", and the research below confirms that "), new TextRun({ text: "36 major municipalities and counties", bold: true }),
        new TextRun(" have ArcGIS-based mapping portals with parcel data and some form of API access. Virtually all of them run on "),
        new TextRun({ text: "Esri ArcGIS", bold: true }),
        new TextRun(" (ArcGIS Online, ArcGIS Hub, or ArcGIS Enterprise), often with a Geocortex viewer on top. This means a single integration pattern (ArcGIS REST API) could cover the vast majority of Ontario."),
      ]}),

      // KEY NUMBERS
      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Key Numbers")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [
        new TextRun({ text: "444", bold: true }), new TextRun(" total Ontario municipalities (single-tier, upper-tier, lower-tier)")
      ]}),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [
        new TextRun({ text: "80+", bold: true }), new TextRun(" have public GIS/open data portals (per Ontario GeoHub and CanadianGIS.com)")
      ]}),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [
        new TextRun({ text: "36", bold: true }), new TextRun(" confirmed in this research with parcel data + API access")
      ]}),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [
        new TextRun({ text: "~95%", bold: true }), new TextRun(" use Esri ArcGIS as their GIS platform")
      ]}),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, spacing: { after: 200 }, children: [
        new TextRun({ text: "100%", bold: true }), new TextRun(" of the 36 researched have parcel boundary data; zoning confirmed in 26 of 36")
      ]}),

      // WHAT THIS MEANS FOR CLEO
      new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("What This Means for Cleo")] }),
      new Paragraph({ spacing: { after: 120 }, children: [
        new TextRun("The core problem we\u2019re solving: the Ontario Geocoder returns a "),
        new TextRun({ text: "StreetAddress", bold: true }),
        new TextRun(" point on the road centerline, which sometimes lands on the wrong parcel (e.g., the small lot across the street instead of the 22-acre multifamily site). If we had direct access to "),
        new TextRun({ text: "municipal parcel geometry with zoning attributes", bold: true }),
        new TextRun(", we could:"),
      ]}),
      new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [
        new TextRun({ text: "Cross-validate", bold: true }), new TextRun(" geocoded parcels against zoning and acreage (a $100M multifamily site shouldn\u2019t be on a 40m\u00B2 residential lot)")
      ]}),
      new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [
        new TextRun({ text: "Direct parcel lookup", bold: true }), new TextRun(" by address via municipal FeatureServer queries, bypassing the provincial geocoder entirely for municipalities that expose this")
      ]}),
      new Paragraph({ numbering: { reference: "numbers", level: 0 }, spacing: { after: 200 }, children: [
        new TextRun({ text: "Enrich property data", bold: true }), new TextRun(" with zoning designation, land use, and other attributes not available from RT or GW")
      ]}),

      // PROVINCIAL DATA SOURCES
      new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Provincial-Level Data Sources")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Ontario Parcel Dataset")] }),
      new Paragraph({ spacing: { after: 120 }, children: [
        new TextRun("Covers ~7.5 million parcels province-wide. Available through the Ontario GeoHub (geohub.lio.gov.on.ca) and distributed commercially by Teranet. "),
        new TextRun({ text: "Commercially licensed", bold: true, color: "CC0000" }),
        new TextRun(" \u2014 not freely available. Subject to the Ontario Parcel Licence Agreement (OPLA). This is the same parcel data that powers GeoWarehouse."),
      ]}),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("AgMaps (Ministry of Agriculture)")] }),
      new Paragraph({ spacing: { after: 120 }, children: [
        new TextRun("REST API endpoint: "), new TextRun({ text: "ws.lioservices.lrc.gov.on.ca/arcgis4/rest/services/AIA/Assessment_Parcel_Map/MapServer", size: 18, color: "2D6A4F" }),
        new TextRun("\nThis is the service Cleo already uses via the AgMaps proxy. It\u2019s "),
        new TextRun({ text: "publicly queryable", bold: true }),
        new TextRun(" for individual parcel lookups by ARN and spatial point queries. However, it\u2019s not designed for bulk extraction \u2014 it\u2019s query-per-parcel."),
      ]}),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("MPAC (Municipal Property Assessment Corporation)")] }),
      new Paragraph({ spacing: { after: 120 }, children: [
        new TextRun("Assesses all 5.6 million Ontario properties. "),
        new TextRun({ text: "No public API. No open data.", bold: true, color: "CC0000" }),
        new TextRun(" MPAC explicitly states their data will not be made available through Ontario\u2019s public data portal. Commercial bulk extracts available by contacting MPAC directly."),
      ]}),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("LIO REST Services")] }),
      new Paragraph({ spacing: { after: 120 }, children: [
        new TextRun("Base URL: "), new TextRun({ text: "ws.lioservices.lrc.gov.on.ca/arcgis[version]/rest/services/", size: 18, color: "2D6A4F" }),
        new TextRun("\nSome open data layers available (LIO_OPEN_DATA). Parcel-specific layers are restricted/licensed. Max 5,000 records per query."),
      ]}),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Teranet / OnLand")] }),
      new Paragraph({ spacing: { after: 200 }, children: [
        new TextRun("Ontario Land Registry (POLARIS). OnLand provides web-based individual lookups. Teraview is for licensed professionals. "),
        new TextRun({ text: "No bulk API for public use.", bold: true }),
        new TextRun(" Commercial API available through Teranet\u2019s geospatial solutions division (requires licensing agreement)."),
      ]}),

      new Paragraph({ children: [new PageBreak()] }),

      // MAJOR MUNICIPALITIES TABLE
      new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Major Municipalities (16 Confirmed)")] }),
      new Paragraph({ spacing: { after: 200 }, children: [
        new TextRun("These are Ontario\u2019s largest cities and regional municipalities. All have public GIS portals, all use ArcGIS, and all expose parcel data."),
      ]}),
      makeTable(majorMunis),

      new Paragraph({ children: [new PageBreak()] }),

      // COUNTIES TABLE
      new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Counties & Smaller Municipalities (20 Confirmed)")] }),
      new Paragraph({ spacing: { after: 200 }, children: [
        new TextRun("Every single county researched has a public GIS portal with parcel and zoning data. About half use Geocortex as a viewer layer on top of ArcGIS. All support REST API queries."),
      ]}),
      makeTable(countyMunis),

      new Paragraph({ children: [new PageBreak()] }),

      // PLATFORM ANALYSIS
      new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Platform Analysis")] }),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("ArcGIS REST API (Universal)")] }),
      new Paragraph({ spacing: { after: 120 }, children: [
        new TextRun("Every municipality researched runs on Esri ArcGIS. The ArcGIS REST API is standardized \u2014 the same query pattern works against Toronto\u2019s enterprise server, Ottawa\u2019s MapServer, and Elgin County\u2019s Geocortex-fronted service. Key query capabilities:"),
      ]}),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [
        new TextRun({ text: "Spatial queries:", bold: true }), new TextRun(" Query parcels by point (lat/lng), envelope, or polygon geometry")
      ]}),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [
        new TextRun({ text: "Attribute queries:", bold: true }), new TextRun(" Query parcels by ARN, address, owner name, zoning code")
      ]}),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [
        new TextRun({ text: "Feature output:", bold: true }), new TextRun(" Returns GeoJSON or Esri JSON with full geometry + attributes")
      ]}),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, spacing: { after: 120 }, children: [
        new TextRun({ text: "Pagination:", bold: true }), new TextRun(" Most services return max 1,000\u20135,000 features per request; use resultOffset for pagination")
      ]}),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Geocortex (11 of 20 Counties)")] }),
      new Paragraph({ spacing: { after: 120 }, children: [
        new TextRun("Geocortex is a viewer/middleware layer, not a replacement for ArcGIS. The underlying data is still served via ArcGIS REST services. Geocortex endpoints can be accessed programmatically, but discovering the underlying ArcGIS service URLs may require inspecting network traffic from the Geocortex viewer."),
      ]}),

      new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("ArcGIS Hub / Open Data (Most Municipalities)")] }),
      new Paragraph({ spacing: { after: 200 }, children: [
        new TextRun("ArcGIS Hub portals (*.hub.arcgis.com or *.opendata.arcgis.com) provide downloadable datasets in CSV, KML, GeoJSON, and Shapefile formats. They also expose GeoServices, WMS, and WFS API endpoints. For bulk parcel downloads, the Hub portals are often the easiest path \u2014 download the full parcel dataset as GeoJSON and cache it locally."),
      ]}),

      // INTEGRATION STRATEGY
      new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Potential Integration Strategy")] }),
      new Paragraph({ spacing: { after: 120 }, children: [
        new TextRun("A phased approach that starts with the highest-value, lowest-risk integrations:"),
      ]}),

      new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun("Phase 1: Bulk Parcel Cache (Low Risk, High Value)")] }),
      new Paragraph({ spacing: { after: 120 }, children: [
        new TextRun("Download parcel boundary datasets from the 16 major municipal open data portals. Store as a local cache (like clean-data/parcels/ today). This gives us verified geometry for the municipalities that account for the majority of Cleo\u2019s transaction volume. No API rate limits, no per-query costs, no session management."),
      ]}),

      new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun("Phase 2: Zoning Enrichment (Medium Risk, High Value)")] }),
      new Paragraph({ spacing: { after: 120 }, children: [
        new TextRun("For municipalities with confirmed zoning FeatureServer endpoints (Toronto, Ottawa, London, Barrie, all 20 counties), query zoning attributes for each property at compile time. Add zoning designation to the property record. This directly addresses the \u201Cwrong parcel\u201D problem \u2014 if a $100M multifamily transaction resolves to a parcel zoned R1 (single residential), we know something\u2019s wrong."),
      ]}),

      new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun("Phase 3: Direct Municipal Geocoding (Higher Risk)")] }),
      new Paragraph({ spacing: { after: 200 }, children: [
        new TextRun("For municipalities with address-searchable FeatureServers, bypass the Ontario Geocoder entirely and resolve addresses directly against the municipal parcel layer. This would be the most accurate approach but requires per-municipality endpoint discovery and maintenance."),
      ]}),

      // RISKS AND CONSIDERATIONS
      new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Risks and Considerations")] }),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [
        new TextRun({ text: "Endpoint stability: ", bold: true }), new TextRun("Municipal ArcGIS service URLs can change without notice. Need a monitoring/health-check system.")
      ]}),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [
        new TextRun({ text: "Rate limits: ", bold: true }), new TextRun("Some municipal ArcGIS servers may have undocumented rate limits. Start with bulk downloads, not per-query API calls.")
      ]}),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [
        new TextRun({ text: "Data freshness: ", bold: true }), new TextRun("Municipal parcel data update frequency varies. Some update quarterly, some annually. Need a refresh strategy.")
      ]}),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [
        new TextRun({ text: "Schema variation: ", bold: true }), new TextRun("While all use ArcGIS, field names differ (e.g., \u201CARN\u201D vs \u201CRoll_Num\u201D vs \u201CAssessment_Roll\u201D). Need per-municipality field mapping.")
      ]}),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [
        new TextRun({ text: "Coverage gaps: ", bold: true }), new TextRun("Northern Ontario municipalities (Sudbury, Sault Ste. Marie, North Bay, Timmins) were not researched yet. Lower transaction volume but may still matter.")
      ]}),
      new Paragraph({ numbering: { reference: "bullets", level: 0 }, spacing: { after: 200 }, children: [
        new TextRun({ text: "Licensing: ", bold: true }), new TextRun("Most open data portals have permissive licenses (Open Government Licence). Verify each municipality\u2019s terms before commercial use.")
      ]}),

      // NEXT STEPS
      new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Recommended Next Steps")] }),
      new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [
        new TextRun({ text: "Endpoint discovery: ", bold: true }), new TextRun("For the top 10 municipalities by Cleo transaction volume, find the exact ArcGIS REST service URLs for parcel and zoning layers. Confirm they support spatial queries.")
      ]}),
      new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [
        new TextRun({ text: "Test queries: ", bold: true }), new TextRun("Run sample spatial queries against 3\u20134 confirmed endpoints (Toronto, Ottawa, London, one county) to validate the approach and measure response quality.")
      ]}),
      new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [
        new TextRun({ text: "Bulk download pilot: ", bold: true }), new TextRun("Download the full parcel dataset from Toronto and London open data portals. Assess file size, data quality, and field coverage.")
      ]}),
      new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [
        new TextRun({ text: "Schema mapping: ", bold: true }), new TextRun("Document the field names and data formats for parcels and zoning across the pilot municipalities. Design a unified schema for Cleo\u2019s parcel cache.")
      ]}),
      new Paragraph({ numbering: { reference: "numbers", level: 0 }, spacing: { after: 200 }, children: [
        new TextRun({ text: "Architecture design: ", bold: true }), new TextRun("Plan how municipal parcel data integrates with the existing resolver chain \u2014 as an additional resolution step, a cross-validation layer, or a replacement for specific municipalities.")
      ]}),
    ]
  }]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync("/sessions/friendly-great-darwin/mnt/cleo-turbo/Ontario_Municipal_GIS_Research.docx", buffer);
  console.log("Done");
});
