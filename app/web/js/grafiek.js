// ECharts-hulpjes. Kleuren komen uit de CSS-tokens, zodat licht en donker vanzelf kloppen.

import { css } from "./basis.js";

const actief = new Set();
const asGetal = new Intl.NumberFormat("nl-NL", { maximumFractionDigits: 2 });

export function grafiek(el) {
  const g = echarts.init(el, null, { renderer: "canvas" });
  actief.add(g);
  return g;
}

export function ruimOp() {
  for (const g of actief) g.dispose();
  actief.clear();
}

export function herschaal() {
  for (const g of actief) g.resize();
}

function samen(a, b) {
  if (b === undefined) return a;
  if (Array.isArray(b) || typeof b !== "object" || b === null || typeof a !== "object" || a === null) return b;
  const uit = { ...a };
  for (const [k, v] of Object.entries(b)) uit[k] = samen(a[k], v);
  return uit;
}

/** Gemeenschappelijke opmaak: rustig raster, assen in gedempte inkt, tooltip als kaart. */
export function basis(extra = {}) {
  const zacht = css("--inkt-3");
  return samen(
    {
      animationDuration: 300,
      textStyle: { fontFamily: css("--font") },
      grid: { left: 4, right: 8, top: 20, bottom: 0, containLabel: true },
      tooltip: {
        trigger: "axis",
        confine: true,
        axisPointer: { type: "shadow", shadowStyle: { color: css("--oppervlak-2"), opacity: 0.7 } },
        backgroundColor: css("--oppervlak"),
        borderColor: css("--lijn-sterk"),
        borderWidth: 1,
        padding: [8, 12],
        textStyle: { color: css("--inkt"), fontSize: 13 },
        extraCssText: "border-radius:10px;box-shadow:0 6px 24px rgb(0 0 0 / .14)",
      },
      xAxis: {
        type: "category",
        axisTick: { show: false },
        axisLine: { lineStyle: { color: css("--lijn-sterk") } },
        axisLabel: { color: zacht, fontSize: 12, hideOverlap: true },
      },
      yAxis: {
        type: "value",
        splitNumber: 4,
        splitLine: { lineStyle: { color: css("--lijn") } },
        axisLabel: { color: zacht, fontSize: 12, formatter: (w) => asGetal.format(w) },
      },
    },
    extra,
  );
}

/** Staafreeks. Afgeronde kant weg van de nullijn; negatieve reeksen hangen eronder. */
export function staven(naam, data, kleur, { stapel, negatief = false, ...rest } = {}) {
  return {
    name: naam,
    type: "bar",
    stack: stapel,
    data,
    barMaxWidth: 18,
    barCategoryGap: "28%",
    itemStyle: { color: kleur, borderRadius: negatief ? [0, 0, 4, 4] : [4, 4, 0, 0] },
    emphasis: { disabled: true },
    ...rest,
  };
}

/** Waarde met eigen kleur per staaf (bijv. prijsniveau of teken). */
export function gekleurd(waarde, kleur) {
  return {
    value: waarde,
    itemStyle: { color: kleur, borderRadius: waarde < 0 ? [0, 0, 4, 4] : [4, 4, 0, 0] },
  };
}

export function lijn(naam, data, kleur, rest = {}) {
  return {
    name: naam,
    type: "line",
    data,
    symbol: "circle",
    symbolSize: 8,
    showSymbol: false,
    connectNulls: false,
    lineStyle: { color: kleur, width: 2 },
    itemStyle: { color: kleur, borderColor: css("--oppervlak"), borderWidth: 2 },
    ...rest,
  };
}

/** Verticale markering op een categorie (bijv. "nu" of "vertrek"). */
export function markering(categorie, tekst) {
  return {
    symbol: "none",
    silent: true,
    animation: false,
    label: { formatter: tekst, color: css("--inkt-2"), fontSize: 11, position: "end", distance: 2 },
    lineStyle: { color: css("--inkt-3"), type: "dashed", width: 1 },
    data: [{ xAxis: categorie }],
  };
}

/** Tooltip-regel met kleurstip. */
export const regel = (kleur, label, waarde) =>
  `<div style="display:flex;align-items:center;gap:8px;min-width:150px">` +
  `<span style="width:10px;height:10px;border-radius:3px;background:${kleur}"></span>` +
  `<span>${label}</span><b style="margin-left:auto;font-weight:500">${waarde}</b></div>`;
